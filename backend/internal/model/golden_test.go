package model_test

import (
	"encoding/json"
	"testing"

	"github.com/freshwood/builder-platform/backend/internal/model"
	"github.com/freshwood/builder-platform/backend/internal/testutil"
)

type engineRow struct {
	Name   string          `json:"name"`
	Inputs json.RawMessage `json:"inputs"`
	Result json.RawMessage `json:"result"`
	Errors []string        `json:"errors"`
}

// TestGoldenRoundtrip decodes every ProjectInputs and ConstructionResult exported from Python
// and checks that encoding reproduces model_dump(mode="json").
func TestGoldenRoundtrip(t *testing.T) {
	var rows, results int
	testutil.ReadJSONL(t, testutil.GoldenPath("engine.jsonl.gz"), func(raw json.RawMessage) {
		rows++
		var row engineRow
		if err := json.Unmarshal(raw, &row); err != nil {
			t.Fatalf("row %d: %v", rows, err)
		}
		t.Run(row.Name, func(t *testing.T) {
			var inputs model.ProjectInputs
			if err := json.Unmarshal(row.Inputs, &inputs); err != nil {
				t.Fatalf("inputs: %v", err)
			}
			got, err := json.Marshal(inputs)
			if err != nil {
				t.Fatal(err)
			}
			testutil.AssertJSONEqual(t, row.Inputs, got, 1e-9)
			if len(row.Result) == 0 || string(row.Result) == "null" {
				if len(row.Errors) == 0 {
					t.Fatalf("row has neither result nor errors")
				}
				return
			}
			results++
			var result model.ConstructionResult
			if err := json.Unmarshal(row.Result, &result); err != nil {
				t.Fatalf("result: %v", err)
			}
			got, err = json.Marshal(result)
			if err != nil {
				t.Fatal(err)
			}
			testutil.AssertJSONEqual(t, row.Result, got, 1e-9)
		})
	})
	if rows == 0 || results == 0 {
		t.Fatalf("no golden rows read (rows=%d, results=%d)", rows, results)
	}
	t.Logf("%d rows, %d results", rows, results)
}
