package agent

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

type textGolden struct {
	Texts []struct {
		Text         string   `json:"text"`
		RouteProject []string `json:"route_project"`
		RouteNew     []string `json:"route_new"`
		Decision     any      `json:"decision"`
	} `json:"texts"`
	Args []struct {
		Text     *string `json:"text"`
		File     string  `json:"file"`
		Quoted   string  `json:"quoted"`
		Balanced string  `json:"balanced"`
		Swapped  string  `json:"swapped"`
		Value    any     `json:"value"`
		Error    string  `json:"error"`
	} `json:"args"`
}

// testdata/text_golden.json was recorded from the former Python implementation.
func loadTextGolden(t *testing.T) textGolden {
	t.Helper()
	raw, err := os.ReadFile("testdata/text_golden.json")
	if err != nil {
		t.Fatal(err)
	}
	var g textGolden
	if err := json.Unmarshal(raw, &g); err != nil {
		t.Fatal(err)
	}
	return g
}

func TestRoutingMatchesPython(t *testing.T) {
	for _, c := range loadTextGolden(t).Texts {
		for _, tc := range []struct {
			has  bool
			want []string
		}{{true, c.RouteProject}, {false, c.RouteNew}} {
			got := RouteMessage(c.Text, tc.has)
			if got.Role != tc.want[0] || got.Reason != tc.want[1] {
				t.Errorf("RouteMessage(%q, %v) = %v, want %v", c.Text, tc.has, got, tc.want)
			}
		}
	}
}

// normalize turns json.Number values into float64 so results compare with decoded goldens.
func normalize(v any) any {
	switch x := v.(type) {
	case json.Number:
		f, _ := x.Float64()
		return f
	case map[string]any:
		out := map[string]any{}
		for k, e := range x {
			out[k] = normalize(e)
		}
		return out
	case []any:
		out := make([]any, len(x))
		for i, e := range x {
			out[i] = normalize(e)
		}
		return out
	}
	return v
}

func TestArgsRepairMatchesPython(t *testing.T) {
	for _, c := range loadTextGolden(t).Args {
		var text string
		if c.Text != nil {
			text = *c.Text
			if got := QuoteBareExpressions(text); got != c.Quoted {
				t.Errorf("QuoteBareExpressions(%q) = %q, want %q", text, got, c.Quoted)
			}
			if got := BalanceBrackets(text, false); got != c.Balanced {
				t.Errorf("BalanceBrackets(%q) = %q, want %q", text, got, c.Balanced)
			}
			if got := BalanceBrackets(text, true); got != c.Swapped {
				t.Errorf("BalanceBrackets(%q, swap) = %q, want %q", text, got, c.Swapped)
			}
		} else {
			raw, err := os.ReadFile("testdata/tool_args/" + c.File)
			if err != nil {
				t.Fatal(err)
			}
			text = string(raw)
		}
		got, err := ParseJSON(text)
		if c.Error != "" {
			if err == nil || err.Error() != c.Error {
				t.Errorf("ParseJSON(%.40q) error = %v, want %q", text, err, c.Error)
			}
			continue
		}
		if err != nil {
			t.Errorf("ParseJSON(%.40q): %v", text, err)
			continue
		}
		if !reflect.DeepEqual(normalize(got), c.Value) {
			t.Errorf("ParseJSON(%.40q) = %v, want %v", text, got, c.Value)
		}
	}
}

func TestExplanationNestedInTheDesignIsHoisted(t *testing.T) {
	raw, err := os.ReadFile("testdata/tool_args/podest_design_explanation.txt")
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := ParseJSON(string(raw))
	if err != nil {
		t.Fatal(err)
	}
	args := HoistNestedArguments(parsed.(map[string]any), map[string]bool{"design": true, "explanation": true})
	if s, _ := args["explanation"].(string); s == "" {
		t.Fatal("explanation not hoisted")
	}
	if _, still := args["design"].(map[string]any)["explanation"]; still {
		t.Fatal("explanation still nested")
	}
}
