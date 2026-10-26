package expr_test

import (
	"bytes"
	"encoding/json"
	"math"
	"sort"
	"strings"
	"testing"

	"github.com/freshwood/builder-platform/backend/internal/engine/expr"
	"github.com/freshwood/builder-platform/backend/internal/testutil"
)

type exprRow struct {
	Env   json.RawMessage `json:"env"`
	Expr  json.RawMessage `json:"expr"`
	Fn    string          `json:"fn"`
	Value json.RawMessage `json:"value"`
	Error *string         `json:"error"`
}

// orderedEnv decodes a JSON object into an Env that keeps the key order (error messages list
// the names in the order of the design).
func orderedEnv(t *testing.T, raw json.RawMessage) *expr.Env {
	t.Helper()
	dec := json.NewDecoder(bytes.NewReader(raw))
	if _, err := dec.Token(); err != nil {
		t.Fatal(err)
	}
	env := expr.NewEnv()
	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			t.Fatal(err)
		}
		var v any
		if err := dec.Decode(&v); err != nil {
			t.Fatal(err)
		}
		switch x := v.(type) {
		case string:
			env.Set(key.(string), expr.Text(x))
		case float64:
			env.Set(key.(string), expr.Number(x))
		default:
			t.Fatalf("env value %v of %v", v, key)
		}
	}
	return env
}

const knownNames = ". Bekannte Namen: "

// sameMessage compares two error messages. The golden file stores the env with sorted keys, so
// the insertion order behind "Bekannte Namen" is lost; that list is compared as a set (and not
// at all when it was cut off, because the cut depends on the order).
func sameMessage(got, want string) bool {
	if got == want {
		return true
	}
	gHead, gList, ok1 := strings.Cut(got, knownNames)
	wHead, wList, ok2 := strings.Cut(want, knownNames)
	if !ok1 || !ok2 || gHead != wHead {
		return false
	}
	if strings.HasSuffix(wList, " …") || strings.HasSuffix(gList, " …") {
		return strings.HasSuffix(wList, " …") == strings.HasSuffix(gList, " …")
	}
	g, w := strings.Split(gList, ", "), strings.Split(wList, ", ")
	sort.Strings(g)
	sort.Strings(w)
	return strings.Join(g, ",") == strings.Join(w, ",")
}

// TestGoldenPython replays every call recorded from the Python evaluator and compares value
// or error message.
func TestGoldenPython(t *testing.T) {
	failed := 0
	n := testutil.ReadJSONL(t, testutil.GoldenPath("expr.jsonl.gz"), func(raw json.RawMessage) {
		if failed >= 20 {
			return
		}
		var row exprRow
		if err := json.Unmarshal(raw, &row); err != nil {
			t.Fatal(err)
		}
		var value any
		if err := json.Unmarshal(row.Expr, &value); err != nil {
			t.Fatal(err)
		}
		env := orderedEnv(t, row.Env)
		var got expr.Scalar
		var err error
		switch row.Fn {
		case "evaluate":
			got, err = expr.EvaluateEnv(value, env)
		case "evaluate_number":
			var f float64
			f, err = expr.EvaluateNumberEnv(value, env)
			got = expr.Number(f)
		default:
			t.Fatalf("unknown fn %q", row.Fn)
		}
		if row.Error != nil {
			if err == nil || !sameMessage(err.Error(), *row.Error) {
				failed++
				t.Errorf("%s(%s): want error %q, got %v (%v)", row.Fn, row.Expr, *row.Error, err, got)
			}
			return
		}
		var want any
		if err := json.Unmarshal(row.Value, &want); err != nil {
			t.Fatal(err)
		}
		if err != nil {
			failed++
			t.Errorf("%s(%s) env %s: want %s, got error %v", row.Fn, row.Expr, row.Env, row.Value, err)
			return
		}
		switch w := want.(type) {
		case string:
			if !got.IsText() || got.Str() != w {
				failed++
				t.Errorf("%s(%s): want %q, got %v", row.Fn, row.Expr, w, got)
			}
		case float64:
			if got.IsText() || (got.Float() != w && math.Abs(got.Float()-w) > 1e-9*math.Abs(w)) ||
				math.Signbit(got.Float()) != math.Signbit(w) {
				failed++
				t.Errorf("%s(%s) env %s: want %v, got %v", row.Fn, row.Expr, row.Env, w, got)
			}
		default:
			t.Fatalf("value %s", row.Value)
		}
	})
	if n == 0 {
		t.Fatal("no golden rows read")
	}
	t.Logf("%d rows", n)
}
