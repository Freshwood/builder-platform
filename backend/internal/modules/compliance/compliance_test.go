package compliance

import (
	"encoding/json"
	"os"
	"testing"
)

// testdata/golden.json was recorded from the former Python implementation.
func TestMatchesPythonImplementation(t *testing.T) {
	raw, err := os.ReadFile("testdata/golden.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Text     string  `json:"text"`
		Redacted string  `json:"redacted"`
		Blocked  bool    `json:"blocked"`
		Topic    *string `json:"topic"`
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		if got := Redact(c.Text); got != c.Redacted {
			t.Errorf("Redact(%q) = %q, want %q", c.Text, got, c.Redacted)
		}
		v := CheckMessage(c.Text)
		want := ""
		if c.Topic != nil {
			want = *c.Topic
		}
		if v.Blocked != c.Blocked || v.Topic != want {
			t.Errorf("CheckMessage(%q) = %v/%q, want %v/%q", c.Text, v.Blocked, v.Topic, c.Blocked, want)
		}
	}
}

func TestTextsMatchPythonImplementation(t *testing.T) {
	raw, err := os.ReadFile("testdata/texts.json")
	if err != nil {
		t.Fatal(err)
	}
	var want struct {
		AI      string   `json:"ai"`
		Label   string   `json:"label"`
		Stmt    string   `json:"stmt"`
		Notices []string `json:"notices"`
		Ver     string   `json:"ver"`
		Resp    []string `json:"resp"`
	}
	if err := json.Unmarshal(raw, &want); err != nil {
		t.Fatal(err)
	}
	if AIChatDisclosure != want.AI || AIContentLabel != want.Label || AIDocumentStatement != want.Stmt || NoticesVersion != want.Ver {
		t.Error("disclosure texts differ")
	}
	for i, n := range want.Notices {
		if DocumentNotices[i] != n {
			t.Errorf("notice %d differs", i)
		}
	}
	for i, r := range want.Resp {
		if Topics[i].Response != r {
			t.Errorf("response %d differs", i)
		}
	}
}
