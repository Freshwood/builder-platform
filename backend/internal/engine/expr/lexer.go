package expr

import (
	"math"
	"math/big"
	"strconv"
	"strings"
	"unicode"
)

// The lexer reproduces the CPython 3.13 tokenizer closely enough that a text is accepted
// exactly when ast.parse(text, mode="eval") accepts it. Every rejection is a syntax error;
// the Python code maps all of them to the same message, so no detail is kept.

type tokKind uint8

const (
	tkEnd tokKind = iota
	tkNewline
	tkName
	tkNumber
	tkString
	tkOp
)

type token struct {
	kind tokKind
	text string // operator text or (normalised) identifier

	// Numbers.
	num      float64
	overflow bool // integer literal too large for a float (OverflowError on use)
	complex  bool // imaginary literal

	// Strings.
	value string
	bytes bool
	fstr  bool
}

// syntaxError aborts lexing or parsing; it is recovered at the parse entry point.
type syntaxError struct{}

func fail() { panic(syntaxError{}) }

var keywords = map[string]bool{
	"False": true, "None": true, "True": true, "and": true, "as": true, "assert": true,
	"async": true, "await": true, "break": true, "class": true, "continue": true, "def": true,
	"del": true, "elif": true, "else": true, "except": true, "finally": true, "for": true,
	"from": true, "global": true, "if": true, "import": true, "in": true, "is": true,
	"lambda": true, "nonlocal": true, "not": true, "or": true, "pass": true, "raise": true,
	"return": true, "try": true, "while": true, "with": true, "yield": true,
}

var ops3 = []string{"**=", "//=", ">>=", "<<=", "..."}

var ops2 = []string{
	"!=", "%=", "&=", "**", "*=", "+=", "-=", "->", "//", "/=", ":=", "<<", "<=", "<>", "==",
	">=", ">>", "@=", "^=", "|=",
}

const ops1 = "%&()*+,-./:;<=>@[]^{|}~"

type lexer struct {
	src   []rune
	pos   int
	depth []rune // open brackets
	toks  []token
	// fmode: lexing the expression part of an f-string replacement field.
	fmode bool
}

func (l *lexer) at(i int) rune {
	if i < 0 || i >= len(l.src) {
		return -1
	}
	return l.src[i]
}

func (l *lexer) peek() rune { return l.at(l.pos) }

func isDigit(c rune) bool  { return c >= '0' && c <= '9' }
func isXDigit(c rune) bool { return isDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F') }
func isASCIILetter(c rune) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
}

// isPotentialIdentStart mirrors the tokenizer: any non-ASCII character may start a name.
func isPotentialIdentStart(c rune) bool { return c >= 128 || isASCIILetter(c) || c == '_' }

func isPotentialIdentChar(c rune) bool { return isPotentialIdentStart(c) || isDigit(c) }

// tokenize splits a whole expression (eval mode).
func tokenize(src []rune) []token {
	l := &lexer{src: src}
	l.run()
	return l.toks
}

// run lexes until the end of input (or, in fmode, until the end of the expression part).
func (l *lexer) run() {
	for {
		c := l.peek()
		for c == ' ' || c == '\t' || c == '\f' {
			l.pos++
			c = l.peek()
		}
		switch {
		case c == -1:
			if len(l.depth) > 0 || l.fmode {
				fail()
			}
			l.emit(token{kind: tkEnd})
			return
		case c == '#':
			if l.fmode {
				fail()
			}
			for l.peek() != -1 && l.peek() != '\n' {
				l.pos++
			}
		case c == '\\':
			if l.at(l.pos+1) != '\n' {
				fail()
			}
			l.pos += 2
		case c == '\n':
			l.pos++
			if len(l.depth) > 0 || l.fmode {
				continue
			}
			l.emit(token{kind: tkNewline})
			l.blankTail()
			l.emit(token{kind: tkEnd})
			return
		case l.fmode && len(l.depth) == 0 && l.fieldEnd(c):
			return
		case isPotentialIdentStart(c):
			l.name()
		case isDigit(c) || (c == '.' && isDigit(l.at(l.pos+1))):
			l.number()
		case c == '\'' || c == '"':
			l.str("")
		default:
			l.op()
		}
	}
}

// fieldEnd reports whether c ends the expression part of an f-string replacement field.
func (l *lexer) fieldEnd(c rune) bool {
	next := l.at(l.pos + 1)
	switch c {
	case '}', ':':
		return true
	case '!', '=':
		return next != '='
	}
	return false
}

// blankTail accepts only blank and comment lines after a top-level newline.
func (l *lexer) blankTail() {
	for {
		c := l.peek()
		for c == ' ' || c == '\t' || c == '\f' {
			l.pos++
			c = l.peek()
		}
		switch c {
		case -1:
			return
		case '\n':
			l.pos++
		case '#':
			for l.peek() != -1 && l.peek() != '\n' {
				l.pos++
			}
		default:
			fail()
		}
	}
}

func (l *lexer) emit(t token) { l.toks = append(l.toks, t) }

func (l *lexer) op() {
	rest := string(l.src[l.pos:min(len(l.src), l.pos+3)])
	text := ""
	for _, o := range ops3 {
		if strings.HasPrefix(rest, o) {
			text = o
			break
		}
	}
	if text == "" {
		for _, o := range ops2 {
			if strings.HasPrefix(rest, o) {
				text = o
				break
			}
		}
	}
	if text == "" {
		c := l.peek()
		if c < 0 || c >= 128 || !strings.ContainsRune(ops1, c) {
			fail()
		}
		text = string(c)
	}
	switch text {
	case "(", "[", "{":
		if len(l.depth) >= 200 {
			fail()
		}
		l.depth = append(l.depth, rune(text[0]))
	case ")", "]", "}":
		if len(l.depth) == 0 {
			fail()
		}
		open := l.depth[len(l.depth)-1]
		if (open == '(' && text != ")") || (open == '[' && text != "]") || (open == '{' && text != "}") {
			fail()
		}
		l.depth = l.depth[:len(l.depth)-1]
	}
	l.pos += len([]rune(text))
	l.emit(token{kind: tkOp, text: text})
}

// --- Names -------------------------------------------------------------------------------

func isStringPrefix(s string) bool {
	switch strings.ToLower(s) {
	case "r", "u", "b", "f", "br", "rb", "fr", "rf":
		return true
	}
	return false
}

func (l *lexer) name() {
	start := l.pos
	for isPotentialIdentChar(l.peek()) {
		l.pos++
	}
	word := string(l.src[start:l.pos])
	if q := l.peek(); (q == '\'' || q == '"') && isStringPrefix(word) {
		l.str(strings.ToLower(word))
		return
	}
	runes := l.src[start:l.pos]
	if !xidStart(runes[0]) {
		fail()
	}
	for _, r := range runes[1:] {
		if !xidContinue(r) {
			fail()
		}
	}
	l.emit(token{kind: tkName, text: normalizeName(word)})
}

func xidStart(r rune) bool {
	if r < 128 {
		return isASCIILetter(r) || r == '_'
	}
	if unicode.Is(unicode.Pattern_Syntax, r) || unicode.Is(unicode.Pattern_White_Space, r) {
		return false
	}
	return unicode.IsLetter(r) || unicode.Is(unicode.Nl, r) || unicode.Is(unicode.Other_ID_Start, r)
}

func xidContinue(r rune) bool {
	if r < 128 {
		return isASCIILetter(r) || r == '_' || isDigit(r)
	}
	if xidStart(r) {
		return true
	}
	if unicode.Is(unicode.Pattern_Syntax, r) || unicode.Is(unicode.Pattern_White_Space, r) {
		return false
	}
	return unicode.In(r, unicode.Mn, unicode.Mc, unicode.Nd, unicode.Pc, unicode.Other_ID_Continue)
}

// normalizeName applies the part of Python's NFKC identifier normalisation that matters in
// practice: full-width ASCII letters, digits and underscore.
func normalizeName(s string) string {
	ascii := true
	for i := 0; i < len(s); i++ {
		if s[i] >= 128 {
			ascii = false
			break
		}
	}
	if ascii {
		return s
	}
	return strings.Map(func(r rune) rune {
		if r >= 0xFF01 && r <= 0xFF5E {
			return r - 0xFF01 + 0x21
		}
		return r
	}, s)
}

// --- Numbers -----------------------------------------------------------------------------

func (l *lexer) decimalTail() {
	for {
		for isDigit(l.peek()) {
			l.pos++
		}
		if l.peek() != '_' {
			return
		}
		l.pos++
		if !isDigit(l.peek()) {
			fail()
		}
	}
}

// verifyEnd mirrors verify_end_of_number: a literal may be followed directly by a keyword
// that can follow a number in valid code, but not by any other name character.
func (l *lexer) verifyEnd(at int) {
	c := l.at(at)
	look := func(s string) bool {
		for i, r := range s {
			if l.at(at+1+i) != r {
				return false
			}
		}
		return true
	}
	ok := false
	switch c {
	case 'a':
		ok = look("nd")
	case 'e':
		ok = look("lse")
	case 'f':
		ok = look("or")
	case 'i':
		c2 := l.at(at + 1)
		ok = c2 == 'f' || c2 == 'n' || c2 == 's'
	case 'o':
		ok = look("r")
	case 'n':
		ok = look("ot")
	}
	if !ok && c >= 0 && c < 128 && isPotentialIdentChar(c) {
		fail()
	}
}

func (l *lexer) radixDigits(valid func(rune) bool, decimalIsError bool) {
	l.pos++ // the radix letter
	for {
		if l.peek() == '_' {
			l.pos++
		}
		if !valid(l.peek()) {
			fail()
		}
		for valid(l.peek()) {
			l.pos++
		}
		if l.peek() != '_' {
			break
		}
	}
	if decimalIsError && isDigit(l.peek()) {
		fail()
	}
	l.verifyEnd(l.pos)
}

func (l *lexer) number() {
	start := l.pos
	isFloat := false
	finish := func(end int, imaginary bool) {
		text := strings.ReplaceAll(string(l.src[start:end]), "_", "")
		t := token{kind: tkNumber, text: text, complex: imaginary}
		if !imaginary {
			t.num, t.overflow = numberValue(text, isFloat)
		}
		l.emit(t)
	}
	c := l.peek()
	if c == '.' {
		l.pos++
		isFloat = true
		goto fraction
	}
	if c == '0' {
		l.pos++
		switch l.peek() {
		case 'x', 'X':
			l.radixDigits(isXDigit, false)
			finish(l.pos, false)
			return
		case 'o', 'O':
			l.radixDigits(func(r rune) bool { return r >= '0' && r <= '7' }, true)
			finish(l.pos, false)
			return
		case 'b', 'B':
			l.radixDigits(func(r rune) bool { return r == '0' || r == '1' }, true)
			finish(l.pos, false)
			return
		}
		nonzero := false
		for {
			if l.peek() == '_' {
				l.pos++
				if !isDigit(l.peek()) {
					fail()
				}
			}
			if l.peek() != '0' {
				break
			}
			l.pos++
		}
		if isDigit(l.peek()) {
			nonzero = true
			l.decimalTail()
		}
		switch l.peek() {
		case '.':
			l.pos++
			isFloat = true
			goto fraction
		case 'e', 'E':
			goto exponent
		case 'j', 'J':
			goto imaginary
		}
		if nonzero {
			fail()
		}
		l.verifyEnd(l.pos)
		finish(l.pos, false)
		return
	}
	l.decimalTail()
	switch l.peek() {
	case '.':
		l.pos++
		isFloat = true
		goto fraction
	case 'e', 'E':
		goto exponent
	case 'j', 'J':
		goto imaginary
	}
	l.verifyEnd(l.pos)
	finish(l.pos, false)
	return

fraction:
	if isDigit(l.peek()) {
		l.decimalTail()
	}
	switch l.peek() {
	case 'e', 'E':
		goto exponent
	case 'j', 'J':
		goto imaginary
	}
	l.verifyEnd(l.pos)
	finish(l.pos, false)
	return

exponent:
	{
		ePos := l.pos
		l.pos++
		switch c := l.peek(); {
		case c == '+' || c == '-':
			l.pos++
			if !isDigit(l.peek()) {
				fail()
			}
		case !isDigit(c):
			// "1else": the number ends before the 'e'.
			l.verifyEnd(ePos)
			l.pos = ePos
			finish(ePos, false)
			return
		}
		isFloat = true
		l.decimalTail()
		if c := l.peek(); c == 'j' || c == 'J' {
			goto imaginary
		}
		l.verifyEnd(l.pos)
		finish(l.pos, false)
		return
	}

imaginary:
	l.pos++
	l.verifyEnd(l.pos)
	finish(l.pos, true)
}

// numberValue converts a literal (underscores removed) like Python's float(literal).
func numberValue(text string, isFloat bool) (float64, bool) {
	if !isFloat && len(text) > 1 && text[0] == '0' {
		base := 0
		switch text[1] {
		case 'x', 'X':
			base = 16
		case 'o', 'O':
			base = 8
		case 'b', 'B':
			base = 2
		}
		if base != 0 {
			n, ok := new(big.Int).SetString(text[2:], base)
			if !ok {
				fail()
			}
			f, _ := new(big.Float).SetInt(n).Float64()
			if math.IsInf(f, 0) {
				return 0, true
			}
			return f, false
		}
	}
	f, err := strconv.ParseFloat(text, 64)
	if err != nil {
		if ne, ok := err.(*strconv.NumError); !ok || ne.Err != strconv.ErrRange {
			fail()
		}
	}
	return f, false
}

// --- Strings -----------------------------------------------------------------------------

func (l *lexer) str(prefix string) {
	raw := strings.Contains(prefix, "r")
	isBytes := strings.Contains(prefix, "b")
	isF := strings.Contains(prefix, "f")
	q := l.peek()
	triple := l.at(l.pos+1) == q && l.at(l.pos+2) == q
	if triple {
		l.pos += 3
	} else {
		l.pos++
	}
	if isF {
		l.fstring(q, triple, raw)
		l.emit(token{kind: tkString, fstr: true})
		return
	}
	start := l.pos
	var end int
	for {
		c := l.peek()
		if c == -1 || (!triple && c == '\n') {
			fail()
		}
		if c == '\\' {
			if l.at(l.pos+1) == -1 {
				fail()
			}
			l.pos += 2
			continue
		}
		if c == q {
			if !triple {
				end = l.pos
				l.pos++
				break
			}
			if l.at(l.pos+1) == q && l.at(l.pos+2) == q {
				end = l.pos
				l.pos += 3
				break
			}
		}
		l.pos++
	}
	body := l.src[start:end]
	if isBytes {
		for _, r := range body {
			if r >= 128 {
				fail()
			}
		}
	}
	value := string(body)
	if !raw {
		value = decodeEscapes(body, isBytes)
	}
	l.emit(token{kind: tkString, value: value, bytes: isBytes})
}

// decodeEscapes applies Python's backslash escapes of a non-raw literal.
func decodeEscapes(body []rune, isBytes bool) string {
	var b strings.Builder
	for i := 0; i < len(body); i++ {
		c := body[i]
		if c != '\\' {
			b.WriteRune(c)
			continue
		}
		i++
		c = body[i]
		switch c {
		case '\n':
		case '\\', '\'', '"':
			b.WriteRune(c)
		case 'a':
			b.WriteByte(7)
		case 'b':
			b.WriteByte(8)
		case 'f':
			b.WriteByte(12)
		case 'n':
			b.WriteByte('\n')
		case 'r':
			b.WriteByte('\r')
		case 't':
			b.WriteByte('\t')
		case 'v':
			b.WriteByte(11)
		case '0', '1', '2', '3', '4', '5', '6', '7':
			v := c - '0'
			for k := 0; k < 2 && i+1 < len(body) && body[i+1] >= '0' && body[i+1] <= '7'; k++ {
				i++
				v = v*8 + body[i] - '0'
			}
			b.WriteRune(v)
		case 'x', 'u', 'U':
			n := map[rune]int{'x': 2, 'u': 4, 'U': 8}[c]
			if isBytes && c != 'x' {
				b.WriteRune('\\')
				b.WriteRune(c)
				continue
			}
			if i+n >= len(body) {
				fail()
			}
			v := 0
			for k := 1; k <= n; k++ {
				d := body[i+k]
				if !isXDigit(d) {
					fail()
				}
				v = v*16 + hexVal(d)
			}
			if v > 0x10FFFF {
				fail()
			}
			i += n
			b.WriteRune(rune(v))
		case 'N':
			if isBytes {
				b.WriteString("\\N")
				continue
			}
			// \N{NAME}: the Unicode name database is not available; the escape is kept as
			// written when it is well-formed.
			if i+1 >= len(body) || body[i+1] != '{' {
				fail()
			}
			j := i + 2
			for j < len(body) && body[j] != '}' {
				j++
			}
			if j >= len(body) || j == i+2 {
				fail()
			}
			b.WriteString(string(body[i-1 : j+1]))
			i = j
		default:
			b.WriteRune('\\')
			b.WriteRune(c)
		}
	}
	return b.String()
}

func hexVal(d rune) int {
	switch {
	case d >= '0' && d <= '9':
		return int(d - '0')
	case d >= 'a' && d <= 'f':
		return int(d-'a') + 10
	default:
		return int(d-'A') + 10
	}
}

// fstring scans an f-string body (PEP 701 rules, simplified) and validates the expressions of
// its replacement fields with the parser.
func (l *lexer) fstring(q rune, triple, raw bool) {
	for {
		c := l.peek()
		switch {
		case c == -1 || (!triple && c == '\n'):
			fail()
		case c == q && (!triple || (l.at(l.pos+1) == q && l.at(l.pos+2) == q)):
			if triple {
				l.pos += 3
			} else {
				l.pos++
			}
			return
		case c == '\\':
			next := l.at(l.pos + 1)
			if next == -1 {
				fail()
			}
			if (raw && next != q && next != '\\') || (!raw && (next == '{' || next == '}')) {
				l.pos++
			} else {
				l.pos += 2
			}
		case c == '{':
			if l.at(l.pos+1) == '{' {
				l.pos += 2
				continue
			}
			l.pos++
			l.field(q, triple)
		case c == '}':
			if l.at(l.pos+1) != '}' {
				fail()
			}
			l.pos += 2
		default:
			l.pos++
		}
	}
}

// field scans one replacement field after its '{' up to and including the closing '}'.
func (l *lexer) field(q rune, triple bool) {
	sub := &lexer{src: l.src, pos: l.pos, fmode: true}
	sub.run()
	sub.emit(token{kind: tkEnd})
	parseFStringExpr(sub.toks)
	l.pos = sub.pos
	if l.peek() == '=' {
		l.pos++
	}
	if l.peek() == '!' {
		l.pos++
		switch l.peek() {
		case 'r', 's', 'a':
			l.pos++
		default:
			fail()
		}
	}
	if l.peek() == ':' {
		l.pos++
		for {
			c := l.peek()
			switch {
			case c == -1 || (!triple && c == '\n') || c == q:
				fail()
			case c == '{':
				l.pos++
				l.field(q, triple)
				continue
			case c == '}':
			default:
				l.pos++
				continue
			}
			break
		}
	}
	if l.peek() != '}' {
		fail()
	}
	l.pos++
}
