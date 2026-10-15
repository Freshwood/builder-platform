package agent

import (
	"context"
	"encoding/json"
	"errors"
	"time"
)

// Provider-neutral conversation format. It follows the structure of the former pydantic-ai
// messages (requests carry user prompts, tool returns and retry prompts; responses carry text,
// thinking and tool calls) and is stored as agent_runs.model_messages.

// Message kinds.
const (
	KindRequest  = "request"
	KindResponse = "response"
)

// Part kinds.
const (
	PartUserPrompt  = "user-prompt"
	PartText        = "text"
	PartThinking    = "thinking"
	PartToolCall    = "tool-call"
	PartToolReturn  = "tool-return"
	PartRetryPrompt = "retry-prompt"
)

// Message is one model request or response.
type Message struct {
	Kind      string    `json:"kind"`
	Parts     []Part    `json:"parts"`
	ModelName string    `json:"model_name,omitempty"`
	Usage     *Usage    `json:"usage,omitempty"`
	Timestamp time.Time `json:"timestamp"`
}

// Part is one element of a message.
type Part struct {
	Kind       string `json:"part_kind"`
	Content    string `json:"content,omitempty"`
	ToolName   string `json:"tool_name,omitempty"`
	ToolCallID string `json:"tool_call_id,omitempty"`
	// Args are the raw tool-call arguments as the model wrote them (JSON text).
	Args string `json:"args,omitempty"`
	// Return is the tool result (tool-return), any JSON value.
	Return json.RawMessage `json:"return,omitempty"`
}

// Usage counts the tokens of one model response.
type Usage struct {
	InputTokens     int `json:"input_tokens"`
	OutputTokens    int `json:"output_tokens"`
	CacheReadTokens int `json:"cache_read_tokens"`
}

// ToolDef describes a tool to the model.
type ToolDef struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	Parameters  map[string]any `json:"parameters"`
}

// ModelRequest is everything a model call needs.
type ModelRequest struct {
	Instructions string
	Messages     []Message
	Tools        []ToolDef
}

// StreamSink receives the response while it is generated.
type StreamSink interface {
	TextDelta(delta string)
	ThinkingDelta(delta string)
	ToolCallStart(id, name string)
	ToolCallDelta(id, delta string)
}

// Model is a chat model with tool calling.
type Model interface {
	Name() string
	// Request runs one model call and returns the complete response message (with Usage).
	Request(ctx context.Context, req ModelRequest, sink StreamSink) (Message, error)
}

// ProviderError is a failed model call (HTTP error, timeout, malformed response). The fallback
// model switches to the next model on it.
type ProviderError struct {
	Status int
	Err    error
}

func (e *ProviderError) Error() string { return e.Err.Error() }
func (e *ProviderError) Unwrap() error { return e.Err }

// FallbackModel uses the first model and falls back to the next on provider errors.
type FallbackModel struct{ Models []Model }

// Name is the name of the first model.
func (f FallbackModel) Name() string { return f.Models[0].Name() }

// Request tries the models in order.
func (f FallbackModel) Request(ctx context.Context, req ModelRequest, sink StreamSink) (Message, error) {
	var last error
	for _, m := range f.Models {
		msg, err := m.Request(ctx, req, sink)
		if err == nil {
			return msg, nil
		}
		var pe *ProviderError
		if !errors.As(err, &pe) || ctx.Err() != nil {
			return Message{}, err
		}
		last = err
	}
	return Message{}, last
}

// toolCalls returns the tool-call parts of a response.
func (m Message) toolCalls() []Part {
	var out []Part
	for _, p := range m.Parts {
		if p.Kind == PartToolCall {
			out = append(out, p)
		}
	}
	return out
}

// text joins the text parts of a response.
func (m Message) text() string {
	s := ""
	for _, p := range m.Parts {
		if p.Kind == PartText {
			s += p.Content
		}
	}
	return s
}
