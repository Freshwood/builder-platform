package expr

import "testing"

// The expected values come from CPython (round, difflib.get_close_matches).
func TestRoundDigits(t *testing.T) {
	for _, c := range []struct{ x, n, want float64 }{
		{0.5, 0, 0}, {1.5, 0, 2}, {2.5, 0, 2}, {-2.5, 0, -2},
		{2.675, 2, 2.67}, {1234.5, -2, 1200}, {1250, -2, 1200}, {1350, -2, 1400}, {-1250, -2, -1200},
		{4, -1, 0}, {123456, 400, 123456},
	} {
		got, err := roundDigits(c.x, c.n)
		if err != nil || got != c.want {
			t.Errorf("round(%v, %v) = %v, %v; want %v", c.x, c.n, got, err, c.want)
		}
	}
	if _, err := roundDigits(1.7e308, -308); err == nil {
		t.Error("round(1.7e308, -308) must overflow")
	}
}

func TestCloseMatch(t *testing.T) {
	for _, c := range []struct {
		word string
		poss []string
		want string
		ok   bool
	}{
		{"surface_type", []string{"width_mm", "surface"}, "surface", true},
		{"appel", []string{"ape", "apple", "peach", "puppy"}, "apple", true},
		{"zzz", []string{"width_mm", "height_mm"}, "", false},
		{"abc", nil, "", false},
		// Equal scores: the greater string wins, like Python's (score, x) tuples.
		{"abc", []string{"abd", "abe"}, "abe", true},
	} {
		got, ok := closeMatch(c.word, c.poss)
		if got != c.want || ok != c.ok {
			t.Errorf("closeMatch(%q, %q) = %q, %v; want %q, %v", c.word, c.poss, got, ok, c.want, c.ok)
		}
	}
}
