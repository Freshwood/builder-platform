// Package testutil holds helpers shared by tests: reading the golden files exported from the
// Python implementation and comparing JSON documents semantically.
package testutil

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"
)

// ModuleRoot returns the directory of the backend Go module (the one holding go.mod).
func ModuleRoot() string {
	_, file, _, ok := runtime.Caller(0)
	if ok {
		// internal/testutil/testutil.go -> module root two levels up.
		dir := filepath.Dir(filepath.Dir(filepath.Dir(file)))
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
	}
	dir, err := os.Getwd()
	if err != nil {
		panic(err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			panic("testutil: go.mod not found")
		}
		dir = parent
	}
}

// GoldenPath resolves a file in backend/testdata/golden, e.g. GoldenPath("engine.jsonl.gz").
func GoldenPath(name string) string {
	return filepath.Join(ModuleRoot(), "testdata", "golden", name)
}

// ReadJSONL calls fn for every non-empty line of a JSON-lines file. Files ending in ".gz" are
// decompressed transparently. It returns the number of lines read.
func ReadJSONL(t testing.TB, path string, fn func(raw json.RawMessage)) int {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("open %s: %v", path, err)
	}
	defer f.Close()
	var r io.Reader = f
	if strings.HasSuffix(path, ".gz") {
		gz, err := gzip.NewReader(f)
		if err != nil {
			t.Fatalf("gunzip %s: %v", path, err)
		}
		defer gz.Close()
		r = gz
	}
	sc := bufio.NewScanner(r)
	sc.Buffer(make([]byte, 0, 1<<20), 1<<30)
	n := 0
	for sc.Scan() {
		line := bytes.TrimSpace(sc.Bytes())
		if len(line) == 0 {
			continue
		}
		n++
		fn(json.RawMessage(append([]byte(nil), line...)))
	}
	if err := sc.Err(); err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return n
}

// ToJSONValue converts v into a generic JSON tree (map[string]any, []any, json.Number, string,
// bool, nil). []byte, json.RawMessage and string are parsed as JSON text; anything else is
// marshalled with encoding/json first.
func ToJSONValue(v any) (any, error) {
	var data []byte
	switch x := v.(type) {
	case json.RawMessage:
		data = x
	case []byte:
		data = x
	case string:
		data = []byte(x)
	default:
		b, err := json.Marshal(v)
		if err != nil {
			return nil, err
		}
		data = b
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var out any
	if err := dec.Decode(&out); err != nil {
		return nil, err
	}
	return out, nil
}

// DiffJSON compares two JSON values semantically: key order is ignored and numbers are compared
// numerically with the relative/absolute tolerance tol. It returns one line per difference,
// each prefixed with the path (e.g. "result.bom.3.total.min").
func DiffJSON(want, got any, tol float64) ([]string, error) {
	w, err := ToJSONValue(want)
	if err != nil {
		return nil, fmt.Errorf("want: %w", err)
	}
	g, err := ToJSONValue(got)
	if err != nil {
		return nil, fmt.Errorf("got: %w", err)
	}
	var out []string
	diffValue("", w, g, tol, &out)
	return out, nil
}

// AssertJSONEqual fails the test when want and got differ semantically (see DiffJSON). At most
// 20 differences are reported.
func AssertJSONEqual(t testing.TB, want, got any, tol float64) {
	t.Helper()
	diffs, err := DiffJSON(want, got, tol)
	if err != nil {
		t.Fatalf("AssertJSONEqual: %v", err)
	}
	if len(diffs) == 0 {
		return
	}
	shown := diffs
	if len(shown) > 20 {
		shown = shown[:20]
	}
	t.Errorf("JSON differs in %d place(s):\n  %s", len(diffs), strings.Join(shown, "\n  "))
}

func join(path, key string) string {
	if path == "" {
		return key
	}
	return path + "." + key
}

func short(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprintf("%v", v)
	}
	s := string(b)
	if len(s) > 120 {
		s = s[:117] + "..."
	}
	return s
}

func numEqual(a, b json.Number, tol float64) bool {
	if a == b {
		return true
	}
	x, err1 := a.Float64()
	y, err2 := b.Float64()
	if err1 != nil || err2 != nil {
		return false
	}
	if x == y {
		return true
	}
	scale := math.Max(1, math.Max(math.Abs(x), math.Abs(y)))
	return math.Abs(x-y) <= tol*scale
}

func diffValue(path string, want, got any, tol float64, out *[]string) {
	label := path
	if label == "" {
		label = "<root>"
	}
	switch w := want.(type) {
	case map[string]any:
		g, ok := got.(map[string]any)
		if !ok {
			*out = append(*out, fmt.Sprintf("%s: want object, got %s", label, short(got)))
			return
		}
		keys := make([]string, 0, len(w)+len(g))
		for k := range w {
			keys = append(keys, k)
		}
		for k := range g {
			if _, ok := w[k]; !ok {
				keys = append(keys, k)
			}
		}
		sort.Strings(keys)
		for _, k := range keys {
			wv, inW := w[k]
			gv, inG := g[k]
			switch {
			case !inG:
				*out = append(*out, fmt.Sprintf("%s: missing (want %s)", join(path, k), short(wv)))
			case !inW:
				*out = append(*out, fmt.Sprintf("%s: unexpected (got %s)", join(path, k), short(gv)))
			default:
				diffValue(join(path, k), wv, gv, tol, out)
			}
		}
	case []any:
		g, ok := got.([]any)
		if !ok {
			*out = append(*out, fmt.Sprintf("%s: want array, got %s", label, short(got)))
			return
		}
		if len(w) != len(g) {
			*out = append(*out, fmt.Sprintf("%s: want %d items, got %d", label, len(w), len(g)))
		}
		for i := 0; i < len(w) && i < len(g); i++ {
			diffValue(join(path, fmt.Sprint(i)), w[i], g[i], tol, out)
		}
	case json.Number:
		g, ok := got.(json.Number)
		if !ok || !numEqual(w, g, tol) {
			*out = append(*out, fmt.Sprintf("%s: want %s, got %s", label, w, short(got)))
		}
	default:
		if want != got {
			*out = append(*out, fmt.Sprintf("%s: want %s, got %s", label, short(want), short(got)))
		}
	}
}
