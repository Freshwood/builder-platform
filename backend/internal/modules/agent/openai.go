package agent

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"time"
)

// OpenAIModel talks to any OpenAI-compatible Chat Completions endpoint (OpenRouter, Mistral,
// Azure OpenAI, vLLM, Ollama …) with streaming and tool calls (ADR-0003). It is a small client
// on purpose: the provider-specific fields (OpenRouter reasoning, cache points) stay visible.
type OpenAIModel struct {
	BaseURL     string
	APIKey      string
	Model       string
	MaxTokens   int
	Temperature float64
	// Reasoning effort for OpenRouter ("off", "minimal", "low", "medium", "high"); empty = none.
	Reasoning string
	HTTP      *http.Client
}

// Name is the configured model name.
func (m *OpenAIModel) Name() string { return m.Model }

func (m *OpenAIModel) openRouter() bool { return strings.Contains(m.BaseURL, "openrouter.ai") }

// RetrySuffix ends every retry prompt sent back to the model.
const RetrySuffix = "\n\nFix the errors and try again."

// toOpenAI maps the conversation to Chat Completions messages.
func (m *OpenAIModel) toOpenAI(req ModelRequest) []map[string]any {
	var out []map[string]any
	cache := m.openRouter()
	content := func(text string, cached bool) any {
		if !cached {
			return text
		}
		// Explicit cache points for providers that need them (Anthropic, Gemini via OpenRouter);
		// OpenAI-style providers cache automatically and ignore them.
		return []map[string]any{{"type": "text", "text": text, "cache_control": map[string]string{"type": "ephemeral"}}}
	}
	if req.Instructions != "" {
		out = append(out, map[string]any{"role": "system", "content": content(req.Instructions, cache)})
	}
	for _, msg := range req.Messages {
		if msg.Kind == KindResponse {
			entry := map[string]any{"role": "assistant"}
			var calls []map[string]any
			text := ""
			for _, p := range msg.Parts {
				switch p.Kind {
				case PartText:
					text += p.Content
				case PartToolCall:
					args := p.Args
					if strings.TrimSpace(args) == "" {
						args = "{}"
					}
					calls = append(calls, map[string]any{
						"id": p.ToolCallID, "type": "function",
						"function": map[string]any{"name": p.ToolName, "arguments": args},
					})
				}
			}
			if text != "" {
				entry["content"] = text
			} else {
				entry["content"] = nil
			}
			if len(calls) > 0 {
				entry["tool_calls"] = calls
			}
			out = append(out, entry)
			continue
		}
		for _, p := range msg.Parts {
			switch p.Kind {
			case PartUserPrompt:
				out = append(out, map[string]any{"role": "user", "content": p.Content})
			case PartToolReturn:
				out = append(out, map[string]any{"role": "tool", "tool_call_id": p.ToolCallID, "content": returnText(p.Return)})
			case PartRetryPrompt:
				if p.ToolCallID != "" {
					out = append(out, map[string]any{"role": "tool", "tool_call_id": p.ToolCallID, "content": p.Content + RetrySuffix})
				} else {
					out = append(out, map[string]any{"role": "user", "content": p.Content + RetrySuffix})
				}
			}
		}
	}
	if cache && len(out) > 1 {
		last := out[len(out)-1]
		if text, ok := last["content"].(string); ok && text != "" && last["role"] != "assistant" {
			last["content"] = content(text, true)
		}
	}
	return out
}

// returnText is the tool result as the model reads it: strings as they are, other values as JSON.
func returnText(raw json.RawMessage) string {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return s
	}
	return string(raw)
}

func (m *OpenAIModel) body(req ModelRequest) map[string]any {
	tools := make([]map[string]any, 0, len(req.Tools))
	for i, t := range req.Tools {
		tool := map[string]any{"type": "function", "function": map[string]any{
			"name": t.Name, "description": t.Description, "parameters": t.Parameters,
		}}
		if m.openRouter() && i == len(req.Tools)-1 {
			tool["cache_control"] = map[string]string{"type": "ephemeral"}
		}
		tools = append(tools, tool)
	}
	body := map[string]any{
		"model":          m.Model,
		"messages":       m.toOpenAI(req),
		"stream":         true,
		"stream_options": map[string]any{"include_usage": true},
	}
	if len(tools) > 0 {
		body["tools"] = tools
	}
	if m.MaxTokens > 0 {
		body["max_tokens"] = m.MaxTokens
	}
	body["temperature"] = m.Temperature
	if m.openRouter() && m.Reasoning != "" {
		if m.Reasoning == "off" {
			body["reasoning"] = map[string]any{"enabled": false}
		} else {
			// Without an explicit reasoning request some models write their thinking into the
			// answer text and stop without calling a tool.
			body["reasoning"] = map[string]any{"effort": m.Reasoning}
		}
	}
	return body
}

type chunk struct {
	Model   string `json:"model"`
	Choices []struct {
		Delta struct {
			Content          *string `json:"content"`
			Reasoning        *string `json:"reasoning"`
			ReasoningContent *string `json:"reasoning_content"`
			ToolCalls        []struct {
				Index    int    `json:"index"`
				ID       string `json:"id"`
				Function struct {
					Name      string `json:"name"`
					Arguments string `json:"arguments"`
				} `json:"function"`
			} `json:"tool_calls"`
		} `json:"delta"`
		FinishReason *string `json:"finish_reason"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens        int `json:"prompt_tokens"`
		CompletionTokens    int `json:"completion_tokens"`
		PromptTokensDetails *struct {
			CachedTokens int `json:"cached_tokens"`
		} `json:"prompt_tokens_details"`
	} `json:"usage"`
	Error *struct {
		Message string `json:"message"`
		Code    any    `json:"code"`
	} `json:"error"`
}

// Request runs one streamed Chat Completions call.
func (m *OpenAIModel) Request(ctx context.Context, req ModelRequest, sink StreamSink) (Message, error) {
	payload, err := json.Marshal(m.body(req))
	if err != nil {
		return Message{}, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(m.BaseURL, "/")+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		return Message{}, err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	if m.APIKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+m.APIKey)
	}
	client := m.HTTP
	if client == nil {
		client = &http.Client{Timeout: 10 * time.Minute}
	}
	resp, err := client.Do(httpReq)
	if err != nil {
		return Message{}, &ProviderError{Err: err}
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4000))
		return Message{}, &ProviderError{Status: resp.StatusCode, Err: fmt.Errorf("status_code: %d, model_name: %s, body: %s", resp.StatusCode, m.Model, body)}
	}

	type call struct {
		id, name string
		args     strings.Builder
	}
	var (
		text, thinking strings.Builder
		calls          = map[int]*call{}
		usage          Usage
		modelName      = m.Model
	)
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 1024*1024), 16*1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		data := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if data == "[DONE]" {
			break
		}
		var c chunk
		if err := json.Unmarshal([]byte(data), &c); err != nil {
			return Message{}, &ProviderError{Err: fmt.Errorf("invalid stream chunk: %w", err)}
		}
		if c.Error != nil {
			return Message{}, &ProviderError{Err: fmt.Errorf("provider error: %s", c.Error.Message)}
		}
		if c.Model != "" {
			modelName = c.Model
		}
		if c.Usage != nil {
			usage.InputTokens = c.Usage.PromptTokens
			usage.OutputTokens = c.Usage.CompletionTokens
			if c.Usage.PromptTokensDetails != nil {
				usage.CacheReadTokens = c.Usage.PromptTokensDetails.CachedTokens
			}
		}
		for _, choice := range c.Choices {
			d := choice.Delta
			if d.Content != nil && *d.Content != "" {
				text.WriteString(*d.Content)
				sink.TextDelta(*d.Content)
			}
			for _, r := range []*string{d.Reasoning, d.ReasoningContent} {
				if r != nil && *r != "" {
					thinking.WriteString(*r)
					sink.ThinkingDelta(*r)
				}
			}
			for _, tc := range d.ToolCalls {
				entry, ok := calls[tc.Index]
				if !ok {
					entry = &call{id: tc.ID, name: tc.Function.Name}
					if entry.id == "" {
						entry.id = fmt.Sprintf("call_%d", tc.Index)
					}
					calls[tc.Index] = entry
					sink.ToolCallStart(entry.id, entry.name)
				} else if entry.name == "" && tc.Function.Name != "" {
					entry.name = tc.Function.Name
				}
				if tc.Function.Arguments != "" {
					entry.args.WriteString(tc.Function.Arguments)
					sink.ToolCallDelta(entry.id, tc.Function.Arguments)
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		if ctx.Err() != nil {
			return Message{}, ctx.Err()
		}
		return Message{}, &ProviderError{Err: err}
	}

	msg := Message{Kind: KindResponse, ModelName: modelName, Usage: &usage, Timestamp: time.Now().UTC()}
	if thinking.Len() > 0 {
		msg.Parts = append(msg.Parts, Part{Kind: PartThinking, Content: thinking.String()})
	}
	if text.Len() > 0 {
		msg.Parts = append(msg.Parts, Part{Kind: PartText, Content: text.String()})
	}
	indexes := make([]int, 0, len(calls))
	for i := range calls {
		indexes = append(indexes, i)
	}
	sort.Ints(indexes)
	for _, i := range indexes {
		c := calls[i]
		msg.Parts = append(msg.Parts, Part{Kind: PartToolCall, ToolName: c.name, ToolCallID: c.id, Args: c.args.String()})
	}
	if len(msg.Parts) == 0 {
		return Message{}, &ProviderError{Err: errors.New("empty model response")}
	}
	return msg, nil
}
