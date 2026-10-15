package agent

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"unicode/utf8"
)

// jsonError is a syntax error with the message and code-point position that Python's json module
// reports. The model reads these texts when a tool call is rejected, so they stay identical.
type jsonError struct {
	Msg string
	Pos int // index in code points, like Python string indices
}

func (e *jsonError) Error() string { return fmt.Sprintf("%s: char %d", e.Msg, e.Pos) }

// decodeJSON parses JSON like Python's json.loads (numbers as json.Number, objects as
// map[string]any, duplicate keys: last wins) and fails with Python's error messages.
func decodeJSON(text string) (any, error) {
	p := &jsonParser{s: []rune(text)}
	p.ws()
	v, err := p.value()
	if err != nil {
		return nil, err
	}
	p.ws()
	if p.i != len(p.s) {
		return nil, &jsonError{"Extra data", p.i}
	}
	return v, nil
}

type jsonParser struct {
	s []rune
	i int
}

func (p *jsonParser) ws() {
	for p.i < len(p.s) {
		switch p.s[p.i] {
		case ' ', '\t', '\n', '\r':
			p.i++
		default:
			return
		}
	}
}

func (p *jsonParser) has(lit string) bool {
	r := []rune(lit)
	if p.i+len(r) > len(p.s) {
		return false
	}
	for k, c := range r {
		if p.s[p.i+k] != c {
			return false
		}
	}
	return true
}

func (p *jsonParser) value() (any, error) {
	if p.i >= len(p.s) {
		return nil, &jsonError{"Expecting value", p.i}
	}
	switch c := p.s[p.i]; {
	case c == '"':
		return p.str()
	case c == '{':
		return p.object()
	case c == '[':
		return p.array()
	case c == 'n' && p.has("null"):
		p.i += 4
		return nil, nil
	case c == 't' && p.has("true"):
		p.i += 4
		return true, nil
	case c == 'f' && p.has("false"):
		p.i += 5
		return false, nil
	case c == 'N' && p.has("NaN"):
		p.i += 3
		return json.Number("NaN"), nil
	case c == 'I' && p.has("Infinity"):
		p.i += 8
		return json.Number("Infinity"), nil
	case c == '-' && p.has("-Infinity"):
		p.i += 9
		return json.Number("-Infinity"), nil
	case c == '-' || (c >= '0' && c <= '9'):
		if n, ok := p.number(); ok {
			return n, nil
		}
	}
	return nil, &jsonError{"Expecting value", p.i}
}

// number follows Python's NUMBER_RE: -?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?
func (p *jsonParser) number() (json.Number, bool) {
	start := p.i
	j := p.i
	if j < len(p.s) && p.s[j] == '-' {
		j++
	}
	digits := func(k int) int {
		for k < len(p.s) && p.s[k] >= '0' && p.s[k] <= '9' {
			k++
		}
		return k
	}
	switch {
	case j < len(p.s) && p.s[j] == '0':
		j++
	case j < len(p.s) && p.s[j] >= '1' && p.s[j] <= '9':
		j = digits(j)
	default:
		return "", false
	}
	if j+1 < len(p.s) && p.s[j] == '.' && p.s[j+1] >= '0' && p.s[j+1] <= '9' {
		j = digits(j + 1)
	}
	if j < len(p.s) && (p.s[j] == 'e' || p.s[j] == 'E') {
		k := j + 1
		if k < len(p.s) && (p.s[k] == '+' || p.s[k] == '-') {
			k++
		}
		if k < len(p.s) && p.s[k] >= '0' && p.s[k] <= '9' {
			j = digits(k)
		}
	}
	p.i = j
	return json.Number(string(p.s[start:j])), true
}

func (p *jsonParser) str() (string, error) {
	start := p.i
	p.i++
	var b strings.Builder
	for {
		if p.i >= len(p.s) {
			return "", &jsonError{"Unterminated string starting at", start}
		}
		c := p.s[p.i]
		switch {
		case c == '"':
			p.i++
			return b.String(), nil
		case c == '\\':
			if p.i+1 >= len(p.s) {
				return "", &jsonError{"Unterminated string starting at", start}
			}
			esc := p.s[p.i+1]
			switch esc {
			case '"', '\\', '/':
				b.WriteRune(esc)
			case 'b':
				b.WriteByte('\b')
			case 'f':
				b.WriteByte('\f')
			case 'n':
				b.WriteByte('\n')
			case 'r':
				b.WriteByte('\r')
			case 't':
				b.WriteByte('\t')
			case 'u':
				r, n, err := p.unicodeEscape(p.i)
				if err != nil {
					return "", err
				}
				b.WriteRune(r)
				p.i += n
				continue
			default:
				return "", &jsonError{fmt.Sprintf("Invalid \\escape: %s", pyRepr(string(esc))), p.i}
			}
			p.i += 2
		case c < 0x20:
			return "", &jsonError{"Invalid control character at", p.i}
		default:
			b.WriteRune(c)
			p.i++
		}
	}
}

// unicodeEscape decodes \uXXXX (with surrogate pairs) at position at; returns rune and length.
func (p *jsonParser) unicodeEscape(at int) (rune, int, error) {
	hex := func(k int) (rune, bool) {
		if k+4 > len(p.s) {
			return 0, false
		}
		v, err := strconv.ParseUint(string(p.s[k:k+4]), 16, 32)
		return rune(v), err == nil
	}
	r, ok := hex(at + 2)
	if !ok {
		return 0, 0, &jsonError{"Invalid \\uXXXX escape", at + 1}
	}
	if r >= 0xd800 && r <= 0xdbff && at+7 < len(p.s) && p.s[at+6] == '\\' && p.s[at+7] == 'u' {
		if low, ok := hex(at + 8); ok && low >= 0xdc00 && low <= 0xdfff {
			return 0x10000 + (r-0xd800)<<10 + (low - 0xdc00), 12, nil
		}
	}
	if !utf8.ValidRune(r) {
		r = utf8.RuneError
	}
	return r, 6, nil
}

func (p *jsonParser) object() (any, error) {
	p.i++ // {
	out := map[string]any{}
	p.ws()
	if p.i < len(p.s) && p.s[p.i] == '}' {
		p.i++
		return out, nil
	}
	for {
		if p.i >= len(p.s) || p.s[p.i] != '"' {
			return nil, &jsonError{"Expecting property name enclosed in double quotes", p.i}
		}
		key, err := p.str()
		if err != nil {
			return nil, err
		}
		p.ws()
		if p.i >= len(p.s) || p.s[p.i] != ':' {
			return nil, &jsonError{"Expecting ':' delimiter", p.i}
		}
		p.i++
		p.ws()
		v, err := p.value()
		if err != nil {
			return nil, err
		}
		out[key] = v
		p.ws()
		if p.i < len(p.s) && p.s[p.i] == '}' {
			p.i++
			return out, nil
		}
		if p.i >= len(p.s) || p.s[p.i] != ',' {
			return nil, &jsonError{"Expecting ',' delimiter", p.i}
		}
		comma := p.i
		p.i++
		p.ws()
		if p.i < len(p.s) && p.s[p.i] == '}' {
			return nil, &jsonError{"Illegal trailing comma before end of object", comma}
		}
	}
}

func (p *jsonParser) array() (any, error) {
	p.i++ // [
	out := []any{}
	p.ws()
	if p.i < len(p.s) && p.s[p.i] == ']' {
		p.i++
		return out, nil
	}
	for {
		v, err := p.value()
		if err != nil {
			return nil, err
		}
		out = append(out, v)
		p.ws()
		if p.i < len(p.s) && p.s[p.i] == ']' {
			p.i++
			return out, nil
		}
		if p.i >= len(p.s) || p.s[p.i] != ',' {
			return nil, &jsonError{"Expecting ',' delimiter", p.i}
		}
		comma := p.i
		p.i++
		p.ws()
		if p.i < len(p.s) && p.s[p.i] == ']' {
			return nil, &jsonError{"Illegal trailing comma before end of array", comma}
		}
	}
}

// pyRepr formats a short string like Python's repr() (single quotes).
func pyRepr(s string) string {
	if strings.Contains(s, "'") && !strings.Contains(s, `"`) {
		return `"` + s + `"`
	}
	return "'" + strings.ReplaceAll(strings.ReplaceAll(s, `\`, `\\`), "'", `\'`) + "'"
}
