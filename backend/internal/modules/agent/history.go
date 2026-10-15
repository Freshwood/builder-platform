package agent

import (
	"encoding/json"
)

// Compaction of the message history before every model request (token budget, ADR-0006).
//
// Without it every request would resend every design the model ever wrote, the material catalog
// and lookups from all earlier turns. The model only needs:
//
//   - earlier turns: what was asked, which tools ran and what came out, but not the bulky
//     arguments (designs) or lookups (catalog, current design); it can fetch them again;
//   - the current turn: everything, except designs that a later attempt has superseded (their
//     engine errors stay, so the model still sees what it already fixed) and the thinking of all
//     but the latest response.
//
// Every submitted design stays complete in agent_runs.design_attempts.

// designTools write a whole design as argument.
var designTools = map[string]bool{"save_design": true}

// lookupTools are read-only lookups whose result can simply be requested again.
var lookupTools = map[string]bool{"list_materials": true, "get_current_design": true}

// Stub texts that replace compacted content.
const (
	DesignStub     = "[gekürzt: früherer Entwurf, aktueller Stand über get_current_design]"
	SupersededStub = "[gekürzt: durch einen späteren Entwurf ersetzt]"
	LookupStub     = "[gekürzt: Ergebnis einer früheren Abfrage, bei Bedarf erneut aufrufen]"
)

// turnStart is the index of the request with the latest user prompt.
func turnStart(messages []Message) int {
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Kind != KindRequest {
			continue
		}
		for _, p := range messages[i].Parts {
			if p.Kind == PartUserPrompt {
				return i
			}
		}
	}
	return 0
}

func lastDesignCall(messages []Message) string {
	for i := len(messages) - 1; i >= 0; i-- {
		if messages[i].Kind != KindResponse {
			continue
		}
		parts := messages[i].Parts
		for k := len(parts) - 1; k >= 0; k-- {
			if parts[k].Kind == PartToolCall && designTools[parts[k].ToolName] {
				return parts[k].ToolCallID
			}
		}
	}
	return ""
}

// stubDesignCall keeps title and new_project of a design call and replaces the design.
func stubDesignCall(p Part, stub string) Part {
	kept := map[string]any{}
	if parsed, err := ParseJSON(p.Args); err == nil {
		if args, ok := parsed.(map[string]any); ok {
			for _, k := range []string{"title", "new_project"} {
				if v, in := args[k]; in {
					kept[k] = v
				}
			}
		}
	}
	kept["design"] = stub
	raw, _ := json.Marshal(kept)
	p.Args = string(raw)
	return p
}

// CompactHistory returns the history as it is sent to the model.
func CompactHistory(messages []Message) []Message {
	start := turnStart(messages)
	keep := lastDesignCall(messages[start:])
	lastResponse := -1
	for i, m := range messages {
		if m.Kind == KindResponse {
			lastResponse = i
		}
	}
	out := make([]Message, 0, len(messages))
	for i, m := range messages {
		earlier := i < start
		switch {
		case m.Kind == KindResponse:
			keepThinking := i == lastResponse && !earlier
			parts := make([]Part, 0, len(m.Parts))
			for _, p := range m.Parts {
				if p.Kind == PartThinking && !keepThinking {
					continue
				}
				if p.Kind == PartToolCall && designTools[p.ToolName] && p.ToolCallID != keep {
					stub := SupersededStub
					if earlier {
						stub = DesignStub
					}
					p = stubDesignCall(p, stub)
				}
				parts = append(parts, p)
			}
			m.Parts = parts
		case earlier:
			parts := make([]Part, len(m.Parts))
			for k, p := range m.Parts {
				if p.Kind == PartToolReturn && lookupTools[p.ToolName] {
					p.Return, _ = json.Marshal(LookupStub)
				}
				parts[k] = p
			}
			m.Parts = parts
		}
		out = append(out, m)
	}
	return out
}
