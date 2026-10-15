package agent

import (
	"fmt"
	"strings"
	"unicode"
)

// Repair of hand-written JSON in tool arguments.
//
// Models write whole designs as JSON by hand. Two mistakes are common and cost every retry,
// because the model reads the error as "pass an object, not a string" and repeats the call:
//
//   - arithmetic written as a bare value, e.g. "at": [0, 0, 18 + i * 116] instead of
//     "18 + i * 116" (the design schema takes such expressions as strings anyway),
//   - one closing brace too many or too few at the end of a long design, or } where a list
//     needs ].
//
// Both are repaired here, in one place, for the raw arguments of every tool call. Anything else
// is reported with its position and the likely cause. Repaired values are still validated and
// checked by the engine; nothing is evaluated here.

// ArgsHint tells the model how expressions and objects are written.
const ArgsHint = "Rechenausdrücke stehen als String in Anführungszeichen, z. B. " +
	`"at": [0, 0, "18 + (i + 1) * 116"]; Objekte als JSON-Objekt, nicht als String.`

var (
	closers = map[rune]rune{'}': '{', ']': '['}
	openers = map[rune]rune{'{': '}', '[': ']'}
)

// stringEnd is the index after the JSON string that opens at start (or the end of the text).
func stringEnd(text []rune, start int) int {
	i := start + 1
	for i < len(text) {
		if text[i] == '\\' {
			i += 2
			continue
		}
		if text[i] == '"' {
			return i + 1
		}
		i++
	}
	return len(text)
}

// valueEnd is the end of a bare value: the next , ] or } outside parentheses and strings.
// It is -1 if the text there is no expression: a string or a colon outside parentheses means the
// JSON is broken in another way (e.g. a missing comma), which must not be hidden.
func valueEnd(text []rune, start int) int {
	depth := 0
	i := start
	for i < len(text) {
		switch c := text[i]; {
		case c == '"' || c == ':':
			if depth == 0 {
				return -1
			}
			if c == '"' {
				i = stringEnd(text, i)
				continue
			}
		case c == '(':
			depth++
		case c == ')':
			depth = max(0, depth-1)
		case (c == ',' || c == ']' || c == '}') && depth == 0:
			return i
		}
		i++
	}
	return i
}

func isJSONLiteral(token string) bool {
	v, err := decodeJSON(token)
	if err != nil {
		return false
	}
	switch v.(type) {
	case map[string]any, []any:
		return false
	}
	return true
}

// QuoteBareExpressions puts bare values that are no JSON literal (18 + i * 116, width_mm) in
// quotes.
func QuoteBareExpressions(input string) string {
	text := []rune(input)
	var out strings.Builder
	expectValue := false
	i := 0
	for i < len(text) {
		c := text[i]
		switch {
		case c == '"':
			end := stringEnd(text, i)
			out.WriteString(string(text[i:end]))
			i, expectValue = end, false
		case c == ':' || c == '[' || c == ',':
			out.WriteRune(c)
			i, expectValue = i+1, true
		case unicode.IsSpace(c):
			out.WriteRune(c)
			i++
		case expectValue && c != '{' && c != '}' && c != ']' && valueEnd(text, i) >= 0:
			stop := valueEnd(text, i)
			token := strings.TrimRightFunc(string(text[i:stop]), unicode.IsSpace)
			if isJSONLiteral(token) {
				out.WriteString(token)
			} else {
				out.WriteString(pyDumpString(token))
			}
			out.WriteString(string(text[i+len([]rune(token)) : stop]))
			i, expectValue = stop, false
		default:
			out.WriteRune(c)
			i, expectValue = i+1, false
		}
	}
	return out.String()
}

// BalanceBrackets fixes closing brackets that do not match the open one and closes brackets left
// open. A mismatched closer is dropped (one brace too many), or with swapMismatched replaced by
// the closer the open bracket needs (} written for ]).
func BalanceBrackets(text string, swapMismatched bool) string {
	var out strings.Builder
	var stack []rune
	inString, escaped := false, false
	for _, c := range text {
		switch {
		case inString:
			switch {
			case escaped:
				escaped = false
			case c == '\\':
				escaped = true
			case c == '"':
				inString = false
			}
		case c == '"':
			inString = true
		case openers[c] != 0:
			stack = append(stack, c)
		case closers[c] != 0:
			if len(stack) == 0 {
				continue
			}
			top := stack[len(stack)-1]
			if top != closers[c] {
				if !swapMismatched {
					continue
				}
				c = openers[top]
			}
			stack = stack[:len(stack)-1]
		}
		out.WriteRune(c)
	}
	for k := len(stack) - 1; k >= 0; k-- {
		out.WriteRune(openers[stack[k]])
	}
	return out.String()
}

// ParseJSON parses hand-written JSON, repairing bare expressions and unbalanced brackets. The
// error names the position, the surrounding text and the likely cause.
func ParseJSON(text string) (any, error) {
	v, err := decodeJSON(text)
	if err == nil {
		return v, nil
	}
	first := err.(*jsonError)
	for _, swap := range []bool{false, true} {
		balanced := BalanceBrackets(text, swap)
		for _, candidate := range []string{balanced, QuoteBareExpressions(balanced)} {
			if v, err := decodeJSON(candidate); err == nil {
				return v, nil
			}
		}
	}
	runes := []rune(text)
	from := max(0, first.Pos-40)
	to := min(len(runes), first.Pos+20)
	return nil, fmt.Errorf("Kein gültiges JSON (%s bei Zeichen %d: …%s…). %s",
		first.Msg, first.Pos, string(runes[from:to]), ArgsHint)
}

// nestable are tool arguments that models wrongly write into the design object.
var nestable = []string{"explanation"}

// HoistNestedArguments moves a tool argument the model nested into "design" back to the top
// level. Only keys that are top-level parameters of the tool are moved; a value given at the top
// level wins over the nested one.
func HoistNestedArguments(args map[string]any, toolParams map[string]bool) map[string]any {
	design := args["design"]
	if s, ok := design.(string); ok {
		parsed, err := ParseJSON(s)
		if err != nil {
			return args
		}
		design = parsed
	}
	obj, ok := design.(map[string]any)
	if !ok {
		return args
	}
	var nested []string
	for _, key := range nestable {
		if _, in := obj[key]; in && toolParams[key] {
			nested = append(nested, key)
		}
	}
	if len(nested) == 0 {
		return args
	}
	rest := map[string]any{}
	for k, v := range obj {
		rest[k] = v
	}
	out := map[string]any{}
	for _, key := range nested {
		out[key] = obj[key]
		delete(rest, key)
	}
	for k, v := range args {
		out[k] = v
	}
	out["design"] = rest
	return out
}

// pyDumpString encodes a string like Python's json.dumps(..., ensure_ascii=False).
func pyDumpString(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}
