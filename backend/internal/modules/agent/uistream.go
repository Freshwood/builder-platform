package agent

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
)

// UIStream writes the Vercel AI SDK "UI message stream" protocol (server-sent events) that the
// browser's useChat hook reads. Every chunk is one `data: {json}` event; the stream ends with
// `data: [DONE]`.
type UIStream struct {
	mu      sync.Mutex
	w       http.ResponseWriter
	flusher http.Flusher
	err     error
	// parts records the assistant message as the browser will have built it, for storage.
	parts []map[string]any
	texts map[string]int // text id -> index in parts
	tools map[string]int // tool call id -> index in parts
}

// StreamHeaders are the response headers of a UI message stream.
var StreamHeaders = map[string]string{
	"Content-Type":                  "text/event-stream",
	"Cache-Control":                 "no-cache",
	"Connection":                    "keep-alive",
	"X-Accel-Buffering":             "no",
	"X-Vercel-Ai-Ui-Message-Stream": "v1",
}

// NewUIStream prepares the response for streaming. w may be nil (offline benchmarks): chunks are
// then only recorded.
func NewUIStream(w http.ResponseWriter) *UIStream {
	s := &UIStream{w: w, texts: map[string]int{}, tools: map[string]int{}}
	if w != nil {
		for k, v := range StreamHeaders {
			w.Header().Set(k, v)
		}
		w.WriteHeader(http.StatusOK)
		s.flusher, _ = w.(http.Flusher)
	}
	return s
}

// Err is the first write error (the client went away).
func (s *UIStream) Err() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.err
}

func (s *UIStream) send(chunk map[string]any) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.record(chunk)
	if s.w == nil || s.err != nil {
		return
	}
	raw, err := json.Marshal(chunk)
	if err != nil {
		s.err = err
		return
	}
	if _, err := fmt.Fprintf(s.w, "data: %s\n\n", raw); err != nil {
		s.err = err
		return
	}
	if s.flusher != nil {
		s.flusher.Flush()
	}
}

// record keeps the assistant parts the browser builds from the chunks (see UIParts).
func (s *UIStream) record(chunk map[string]any) {
	switch chunk["type"] {
	case "text-start":
		s.texts[chunk["id"].(string)] = len(s.parts)
		s.parts = append(s.parts, map[string]any{"type": "text", "text": "", "state": "streaming"})
	case "text-delta":
		if i, ok := s.texts[chunk["id"].(string)]; ok {
			s.parts[i]["text"] = s.parts[i]["text"].(string) + chunk["delta"].(string)
		}
	case "text-end":
		if i, ok := s.texts[chunk["id"].(string)]; ok {
			s.parts[i]["state"] = "done"
		}
	case "reasoning-start":
		s.texts[chunk["id"].(string)] = len(s.parts)
		s.parts = append(s.parts, map[string]any{"type": "reasoning", "text": "", "state": "streaming"})
	case "reasoning-delta":
		if i, ok := s.texts[chunk["id"].(string)]; ok {
			s.parts[i]["text"] = s.parts[i]["text"].(string) + chunk["delta"].(string)
		}
	case "reasoning-end":
		if i, ok := s.texts[chunk["id"].(string)]; ok {
			s.parts[i]["state"] = "done"
		}
	case "tool-input-available":
		id := chunk["toolCallId"].(string)
		part := map[string]any{
			"type":       "tool-" + chunk["toolName"].(string),
			"toolCallId": id,
			"state":      "input-available",
			"input":      chunk["input"],
			// Stored like the former implementation did; the client ignores it.
			"providerExecuted": false,
		}
		if i, ok := s.tools[id]; ok {
			s.parts[i] = part
		} else {
			s.tools[id] = len(s.parts)
			s.parts = append(s.parts, part)
		}
	case "tool-output-available":
		if i, ok := s.tools[chunk["toolCallId"].(string)]; ok {
			s.parts[i]["state"] = "output-available"
			s.parts[i]["output"] = chunk["output"]
		}
	case "tool-output-error":
		if i, ok := s.tools[chunk["toolCallId"].(string)]; ok {
			s.parts[i]["state"] = "output-error"
			s.parts[i]["errorText"] = chunk["errorText"]
		}
	}
}

// UIParts are the parts of the assistant message as the browser shows them (stored with the
// run so the chat can be rebuilt after a reload).
func (s *UIStream) UIParts() []map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]map[string]any, len(s.parts))
	copy(out, s.parts)
	return out
}

// Start opens the assistant message.
func (s *UIStream) Start(messageID string) {
	chunk := map[string]any{"type": "start"}
	if messageID != "" {
		chunk["messageId"] = messageID
	}
	s.send(chunk)
}

// StartStep opens one model request.
func (s *UIStream) StartStep() { s.send(map[string]any{"type": "start-step"}) }

// FinishStep closes one model request.
func (s *UIStream) FinishStep() { s.send(map[string]any{"type": "finish-step"}) }

// TextStart opens a text part.
func (s *UIStream) TextStart(id string) { s.send(map[string]any{"type": "text-start", "id": id}) }

// TextDelta appends to a text part.
func (s *UIStream) TextDelta(id, delta string) {
	s.send(map[string]any{"type": "text-delta", "id": id, "delta": delta})
}

// TextEnd closes a text part.
func (s *UIStream) TextEnd(id string) { s.send(map[string]any{"type": "text-end", "id": id}) }

// ReasoningStart opens a reasoning part.
func (s *UIStream) ReasoningStart(id string) {
	s.send(map[string]any{"type": "reasoning-start", "id": id})
}

// ReasoningDelta appends to a reasoning part.
func (s *UIStream) ReasoningDelta(id, delta string) {
	s.send(map[string]any{"type": "reasoning-delta", "id": id, "delta": delta})
}

// ReasoningEnd closes a reasoning part.
func (s *UIStream) ReasoningEnd(id string) { s.send(map[string]any{"type": "reasoning-end", "id": id}) }

// ToolInputStart announces a tool call.
func (s *UIStream) ToolInputStart(id, name string) {
	s.send(map[string]any{"type": "tool-input-start", "toolCallId": id, "toolName": name})
}

// ToolInputDelta streams raw argument text.
func (s *UIStream) ToolInputDelta(id, delta string) {
	s.send(map[string]any{"type": "tool-input-delta", "toolCallId": id, "inputTextDelta": delta})
}

// ToolInputAvailable delivers the parsed arguments.
func (s *UIStream) ToolInputAvailable(id, name string, input any) {
	s.send(map[string]any{"type": "tool-input-available", "toolCallId": id, "toolName": name, "input": input})
}

// ToolOutput delivers the tool result.
func (s *UIStream) ToolOutput(id string, output any) {
	s.send(map[string]any{"type": "tool-output-available", "toolCallId": id, "output": output})
}

// ToolError reports a tool call that failed before it produced output.
func (s *UIStream) ToolError(id, text string) {
	s.send(map[string]any{"type": "tool-output-error", "toolCallId": id, "errorText": text})
}

// Error reports a failed run.
func (s *UIStream) Error(text string) { s.send(map[string]any{"type": "error", "errorText": text}) }

// Finish closes the message and the stream.
func (s *UIStream) Finish() {
	s.send(map[string]any{"type": "finish"})
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.w != nil && s.err == nil {
		if _, err := fmt.Fprint(s.w, "data: [DONE]\n\n"); err != nil {
			s.err = err
		}
		if s.flusher != nil {
			s.flusher.Flush()
		}
	}
}
