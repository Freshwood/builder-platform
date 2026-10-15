package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type recordingSink struct{ text, thinking, args strings.Builder }

func (r *recordingSink) TextDelta(d string)            { r.text.WriteString(d) }
func (r *recordingSink) ThinkingDelta(d string)        { r.thinking.WriteString(d) }
func (r *recordingSink) ToolCallStart(id, name string) {}
func (r *recordingSink) ToolCallDelta(id, d string)    { r.args.WriteString(d) }

func TestOpenAIModelStreamsTextReasoningAndToolCalls(t *testing.T) {
	var body map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(raw, &body)
		if r.Header.Get("Authorization") != "Bearer key" {
			t.Errorf("missing auth header")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		for _, c := range []string{
			`{"model":"x/y-2","choices":[{"delta":{"reasoning":"Denke…"}}]}`,
			`{"choices":[{"delta":{"content":"Gern"}}]}`,
			`{"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"save_design","arguments":"{\"de"}}]}}]}`,
			`{"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"sign\": {}}"}}]}}]}`,
			`{"choices":[],"usage":{"prompt_tokens":100,"completion_tokens":20,"prompt_tokens_details":{"cached_tokens":80}}}`,
		} {
			fmt.Fprintf(w, "data: %s\n\n", c)
		}
		fmt.Fprint(w, "data: [DONE]\n\n")
	}))
	defer srv.Close()
	m := &OpenAIModel{BaseURL: srv.URL + "/openrouter.ai/api/v1", APIKey: "key", Model: "x/y", Reasoning: "low", MaxTokens: 100}
	sink := &recordingSink{}
	msg, err := m.Request(context.Background(), ModelRequest{
		Instructions: "System",
		Messages:     []Message{{Kind: KindRequest, Parts: []Part{{Kind: PartUserPrompt, Content: "Regal"}}}},
		Tools:        []ToolDef{{Name: "save_design", Description: "d", Parameters: map[string]any{"type": "object"}}},
	}, sink)
	if err != nil {
		t.Fatal(err)
	}
	if msg.ModelName != "x/y-2" || msg.Usage.InputTokens != 100 || msg.Usage.CacheReadTokens != 80 {
		t.Fatalf("msg = %+v", msg)
	}
	calls := msg.toolCalls()
	if len(calls) != 1 || calls[0].Args != `{"design": {}}` || calls[0].ToolCallID != "c1" {
		t.Fatalf("calls = %+v", calls)
	}
	if sink.text.String() != "Gern" || sink.thinking.String() != "Denke…" {
		t.Fatalf("sink = %q %q", sink.text.String(), sink.thinking.String())
	}
	if body["reasoning"].(map[string]any)["effort"] != "low" {
		t.Fatalf("reasoning not requested: %v", body["reasoning"])
	}
	messages := body["messages"].([]any)
	system := messages[0].(map[string]any)["content"].([]any)[0].(map[string]any)
	if system["cache_control"] == nil {
		t.Fatal("system prompt without cache point")
	}
}

func TestOpenAIModelReportsHTTPErrorsAsProviderErrors(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"overloaded"}`, http.StatusServiceUnavailable)
	}))
	defer srv.Close()
	m := &OpenAIModel{BaseURL: srv.URL, Model: "m"}
	_, err := m.Request(context.Background(), ModelRequest{}, &recordingSink{})
	var pe *ProviderError
	if err == nil || !asProvider(err, &pe) || pe.Status != 503 {
		t.Fatalf("err = %v", err)
	}
}

func asProvider(err error, target **ProviderError) bool {
	pe, ok := err.(*ProviderError)
	if ok {
		*target = pe
	}
	return ok
}
