// Package expr evaluates the arithmetic expressions used in assembly designs.
//
// It is a port of calc_engine/assembly/expr.py. Only a tiny, side-effect free subset of
// Python syntax is accepted (numbers, names, arithmetic, comparisons, boolean logic and a few
// functions). Anything else is rejected with a message the LLM can act on; the messages are
// the German texts of the Python implementation, byte for byte.
//
// Expressions evaluate to a number or, for choice parameters, to text. Text exists only so
// that conditions can ask which option is set ("surface_type == 'boards'"); it can never be
// used as a measurement, EvaluateNumber rejects that.
//
// Like the Python version, every number is a float64: Python's evaluator converts each
// constant and each result with float(), so integer and boolean values never survive as such.
package expr

import (
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"unicode"
	"unicode/utf8"
)

// MaxLength is the longest accepted expression in characters (code points, after trimming).
const MaxLength = 300

// Kind tells the two kinds of Scalar apart.
type Kind uint8

const (
	// KindNumber is a measurement or count (Python float).
	KindNumber Kind = iota
	// KindText is the value of a choice parameter (Python str).
	KindText
)

// Scalar is what an expression evaluates to: a number or the text of a choice parameter.
type Scalar struct {
	kind Kind
	num  float64
	text string
}

// Number returns a numeric Scalar.
func Number(f float64) Scalar { return Scalar{kind: KindNumber, num: f} }

// Int returns a numeric Scalar for an integer (Python float(int), rounded to nearest even).
func Int(i int64) Scalar { return Scalar{kind: KindNumber, num: float64(i)} }

// Bool returns 1 or 0 like Python float(bool).
func Bool(b bool) Scalar {
	if b {
		return Number(1)
	}
	return Number(0)
}

// Text returns a text Scalar (a choice value).
func Text(s string) Scalar { return Scalar{kind: KindText, text: s} }

// Kind reports whether s is a number or text.
func (s Scalar) Kind() Kind { return s.kind }

// IsText reports whether s is a choice value.
func (s Scalar) IsText() bool { return s.kind == KindText }

// Float returns the number (0 for text).
func (s Scalar) Float() float64 { return s.num }

// Str returns the text ("" for numbers).
func (s Scalar) Str() string { return s.text }

// String formats s like Python's str(): text as is, numbers with repr(float).
func (s Scalar) String() string {
	if s.kind == KindText {
		return s.text
	}
	return FormatFloat(s.num)
}

// FormatFloat formats f like Python's repr(float).
func FormatFloat(f float64) string {
	switch {
	case math.IsInf(f, 1):
		return "inf"
	case math.IsInf(f, -1):
		return "-inf"
	case math.IsNaN(f):
		return "nan"
	}
	s := strconv.FormatFloat(f, 'r'+0*'g', -1, 64)
	_ = s
	// repr uses the shortest round-trip digits, switching to exponent form outside
	// 1e-4 <= |f| < 1e16.
	digits := strconv.FormatFloat(f, 'e', -1, 64)
	mant, expPart, _ := strings.Cut(digits, "e")
	exp, _ := strconv.Atoi(expPart)
	neg := strings.HasPrefix(mant, "-")
	mant = strings.TrimPrefix(mant, "-")
	ds := strings.Replace(mant, ".", "", 1)
	var out string
	if exp < -4 || exp >= 16 {
		out = ds[:1]
		if len(ds) > 1 {
			out += "." + ds[1:]
		}
		sign := "+"
		if exp < 0 {
			sign = "-"
			exp = -exp
		}
		out += fmt.Sprintf("e%s%02d", sign, exp)
	} else if exp < 0 {
		out = "0." + strings.Repeat("0", -exp-1) + ds
	} else if len(ds) <= exp+1 {
		out = ds + strings.Repeat("0", exp+1-len(ds)) + ".0"
	} else {
		out = ds[:exp+1] + "." + ds[exp+1:]
	}
	if neg {
		out = "-" + out
	}
	return out
}

// IsTruthy is the truthiness of an expression result: numbers as usual (NaN is true), any
// non-empty text is true.
func IsTruthy(s Scalar) bool {
	if s.kind == KindText {
		return s.text != ""
	}
	return s.num != 0
}

// ExprError is a rejected expression; Error() is the exact Python message.
type ExprError struct {
	Msg string
}

func (e *ExprError) Error() string { return e.Msg }

// OverflowError mirrors the Python OverflowError that the Python evaluator does not catch
// (int(inf) in round(), floor(inf), an integer literal beyond the float range).
type OverflowError struct {
	Msg string
}

func (e *OverflowError) Error() string { return e.Msg }

func exprErr(format string, args ...any) error {
	return &ExprError{Msg: fmt.Sprintf(format, args...)}
}

// Env is an ordered parameter environment. Python dicts keep insertion order and the "known
// names" in error messages are listed in that order, so the order is part of the contract.
type Env struct {
	names  []string
	values map[string]Scalar
}

// NewEnv returns an empty environment.
func NewEnv() *Env { return &Env{values: map[string]Scalar{}} }

// EnvFromMap builds an environment from a map; names are ordered alphabetically.
func EnvFromMap(m map[string]Scalar) *Env {
	e := NewEnv()
	names := make([]string, 0, len(m))
	for k := range m {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		e.Set(k, m[k])
	}
	return e
}

// Set adds or replaces a value; a new name goes to the end of the order.
func (e *Env) Set(name string, v Scalar) {
	if _, ok := e.values[name]; !ok {
		e.names = append(e.names, name)
	}
	e.values[name] = v
}

// Get returns the value of name.
func (e *Env) Get(name string) (Scalar, bool) {
	if e == nil {
		return Scalar{}, false
	}
	v, ok := e.values[name]
	return v, ok
}

// Names returns the names in insertion order.
func (e *Env) Names() []string {
	if e == nil {
		return nil
	}
	return append([]string(nil), e.names...)
}

// Len returns the number of names.
func (e *Env) Len() int {
	if e == nil {
		return 0
	}
	return len(e.names)
}

// Clone returns an independent copy.
func (e *Env) Clone() *Env {
	c := NewEnv()
	if e != nil {
		for _, k := range e.names {
			c.Set(k, e.values[k])
		}
	}
	return c
}

// Evaluate evaluates a number or expression string against env (parameter values). Value may
// be a string (expression), any Go integer or float type, bool, json.Number or Scalar. Names
// in error messages are listed alphabetically; use EvaluateEnv to keep the design's order.
func Evaluate(value any, env map[string]Scalar) (Scalar, error) {
	return EvaluateEnv(value, EnvFromMap(env))
}

// EvaluateNumber is like Evaluate, but for places that need a measurement (sizes, counts,
// angles).
func EvaluateNumber(value any, env map[string]Scalar) (float64, error) {
	return EvaluateNumberEnv(value, EnvFromMap(env))
}

// EvaluateEnv is Evaluate with an ordered environment (port of expr.evaluate).
func EvaluateEnv(value any, env *Env) (Scalar, error) {
	var source string
	switch v := value.(type) {
	case string:
		source = v
	case Scalar:
		if v.kind == KindNumber {
			return v, nil
		}
		source = v.text
	case bool:
		return Bool(v), nil
	case float64:
		return Number(v), nil
	case float32:
		return Number(float64(v)), nil
	case int:
		return Number(float64(v)), nil
	case int8:
		return Number(float64(v)), nil
	case int16:
		return Number(float64(v)), nil
	case int32:
		return Number(float64(v)), nil
	case int64:
		return Number(float64(v)), nil
	case uint:
		return Number(float64(v)), nil
	case uint8:
		return Number(float64(v)), nil
	case uint16:
		return Number(float64(v)), nil
	case uint32:
		return Number(float64(v)), nil
	case uint64:
		return Number(float64(v)), nil
	case json.Number:
		f, err := strconv.ParseFloat(string(v), 64)
		if err != nil {
			return Scalar{}, fmt.Errorf("expr: invalid number %q", string(v))
		}
		return Number(f), nil
	default:
		return Scalar{}, fmt.Errorf("expr: unsupported value type %T", value)
	}
	tree, err := parse(pyStrip(source))
	if err != nil {
		return Scalar{}, err
	}
	ev := evaluator{env: env, source: source}
	return ev.eval(tree)
}

// EvaluateNumberEnv is EvaluateNumber with an ordered environment (port of
// expr.evaluate_number).
func EvaluateNumberEnv(value any, env *Env) (float64, error) {
	result, err := EvaluateEnv(value, env)
	if err != nil {
		return 0, err
	}
	if result.kind != KindNumber {
		return 0, exprErr("'%s' ist eine Auswahl, keine Zahl – für Maße einen anderen Parameter "+
			"oder den Auswahlwert als Material-Platzhalter {...} verwenden", result.text)
	}
	return result.num, nil
}

// --- Parsing -----------------------------------------------------------------------------

type parsed struct {
	tree *node
	err  error
}

const maxCached = 20000

var (
	cache     sync.Map
	cacheSize atomic.Int64
)

// parse ports expr._parse (including its cache).
func parse(source string) (*node, error) {
	if c, ok := cache.Load(source); ok {
		p := c.(parsed)
		return p.tree, p.err
	}
	tree, err := parseUncached(source)
	if cacheSize.Load() < maxCached {
		if _, loaded := cache.LoadOrStore(source, parsed{tree, err}); !loaded {
			cacheSize.Add(1)
		}
	}
	return tree, err
}

func parseUncached(source string) (*node, error) {
	if utf8.RuneCountInString(source) > MaxLength {
		return nil, exprErr("Ausdruck zu lang (max. %d Zeichen)", MaxLength)
	}
	// Material placeholders look like "{wood}"; models often carry that style over into
	// expressions ("{height_mm} - 130"), so a braced name is read as the plain name.
	text := subPlaceholders([]rune(source))
	// "if" is a Python keyword; accept the spreadsheet-style if(cond, a, b) anyway.
	text = subIfCalls(text)
	tree, ok := parseSource(normalizeNewlines(text))
	if !ok {
		hint := ""
		if strings.Contains(source, "?") {
			hint = " – statt 'a ? b : c' bitte if(a, b, c) schreiben"
		}
		return nil, exprErr("Ungültiger Ausdruck '%s'%s", source, hint)
	}
	return tree, nil
}

// isPySpace is Python's str.isspace() / re's \s for one character.
func isPySpace(r rune) bool { return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f) }

// isPyWord is re's \w for str patterns.
func isPyWord(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

func pyStrip(s string) string { return strings.TrimFunc(s, isPySpace) }

func isIdentASCIIStart(r rune) bool { return isASCIILetter(r) || r == '_' }

// subPlaceholders is re.sub(r"\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", r"\1", text).
func subPlaceholders(src []rune) []rune {
	out := make([]rune, 0, len(src))
	for i := 0; i < len(src); {
		if src[i] == '{' {
			j := i + 1
			for j < len(src) && isPySpace(src[j]) {
				j++
			}
			if j < len(src) && isIdentASCIIStart(src[j]) {
				start := j
				for j < len(src) && (isIdentASCIIStart(src[j]) || isDigit(src[j])) {
					j++
				}
				end := j
				for j < len(src) && isPySpace(src[j]) {
					j++
				}
				if j < len(src) && src[j] == '}' {
					out = append(out, src[start:end]...)
					i = j + 1
					continue
				}
			}
		}
		out = append(out, src[i])
		i++
	}
	return out
}

// subIfCalls is re.sub(r"\bif\s*\(", "_if(", text).
func subIfCalls(src []rune) []rune {
	out := make([]rune, 0, len(src)+8)
	for i := 0; i < len(src); {
		if src[i] == 'i' && i+1 < len(src) && src[i+1] == 'f' && (i == 0 || !isPyWord(src[i-1])) {
			j := i + 2
			for j < len(src) && isPySpace(src[j]) {
				j++
			}
			if j < len(src) && src[j] == '(' {
				out = append(out, []rune("_if(")...)
				i = j + 1
				continue
			}
		}
		out = append(out, src[i])
		i++
	}
	return out
}

// normalizeNewlines translates \r\n and \r to \n like CPython's string tokenizer.
func normalizeNewlines(src []rune) []rune {
	out := make([]rune, 0, len(src))
	for i := 0; i < len(src); i++ {
		if src[i] == '\r' {
			out = append(out, '\n')
			if i+1 < len(src) && src[i+1] == '\n' {
				i++
			}
			continue
		}
		out = append(out, src[i])
	}
	return out
}

// --- Evaluation --------------------------------------------------------------------------

var functionNames = []string{"min", "max", "abs", "round", "floor", "ceil", "sqrt", "sin", "cos", "tan"}

func isFunction(name string) bool {
	for _, f := range functionNames {
		if f == name {
			return true
		}
	}
	return false
}

const maxListedNames = 15

var allowed = "+ - * / // %, Vergleiche, and/or/not, if(a, b, c), " + strings.Join(functionNames, ", ")

type evaluator struct {
	env    *Env
	source string
}

func (ev *evaluator) number(v Scalar) (float64, error) {
	if v.kind != KindNumber {
		return 0, exprErr("'%s' ist eine Auswahl, keine Zahl – in '%s' nicht rechenbar", v.text, ev.source)
	}
	return v.num, nil
}

func (ev *evaluator) evalNumber(n *node) (float64, error) {
	v, err := ev.eval(n)
	if err != nil {
		return 0, err
	}
	return ev.number(v)
}

func (ev *evaluator) eval(n *node) (Scalar, error) {
	switch n.kind {
	case kNum:
		if n.overflow {
			return Scalar{}, &OverflowError{Msg: "int too large to convert to float"}
		}
		return Number(n.num), nil
	case kStr:
		return Text(n.str), nil
	case kName:
		switch n.str {
		case "true", "True":
			return Number(1), nil
		case "false", "False":
			return Number(0), nil
		}
		v, ok := ev.env.Get(n.str)
		if !ok {
			return Scalar{}, &ExprError{Msg: ev.unknownName(n.str)}
		}
		return v, nil
	case kUnary:
		switch n.op {
		case "-", "+":
			x, err := ev.evalNumber(n.kids[0])
			if err != nil {
				return Scalar{}, err
			}
			if n.op == "-" {
				x = -x
			}
			return Number(x), nil
		case "not":
			v, err := ev.eval(n.kids[0])
			if err != nil {
				return Scalar{}, err
			}
			return Bool(!IsTruthy(v)), nil
		}
	case kBinary:
		switch n.op {
		case "+", "-", "*", "/", "//", "%":
			a, err := ev.evalNumber(n.kids[0])
			if err != nil {
				return Scalar{}, err
			}
			b, err := ev.evalNumber(n.kids[1])
			if err != nil {
				return Scalar{}, err
			}
			return Number(binary(n.op, a, b)), ev.divisionCheck(n.op, b)
		}
	case kBool:
		want := n.op == "or"
		for _, k := range n.kids {
			v, err := ev.eval(k)
			if err != nil {
				return Scalar{}, err
			}
			if IsTruthy(v) == want {
				return Bool(want), nil
			}
		}
		return Bool(!want), nil
	case kCompare:
		current, err := ev.eval(n.kids[0])
		if err != nil {
			return Scalar{}, err
		}
		complete := true
		for i, op := range n.ops {
			if !isCompareOp(op) {
				complete = false
				break
			}
			nxt, err := ev.eval(n.kids[i+1])
			if err != nil {
				return Scalar{}, err
			}
			// Comparing text with a number is a modelling mistake, not a false condition.
			if current.IsText() != nxt.IsText() {
				text := nxt.text
				if current.IsText() {
					text = current.text
				}
				return Scalar{}, exprErr("'%s' ist eine Auswahl – in '%s' nicht mit einer Zahl vergleichbar", text, ev.source)
			}
			// Text is only meaningful for equality; "a" < "b" is never what was meant.
			if current.IsText() && op != "==" && op != "!=" {
				return Scalar{}, exprErr("Auswahlwerte lassen sich nur mit == oder != vergleichen, nicht in '%s'", ev.source)
			}
			if !compare(op, current, nxt) {
				return Number(0), nil
			}
			current = nxt
		}
		if complete {
			return Number(1), nil
		}
	case kIfExp:
		test, err := ev.eval(n.kids[0])
		if err != nil {
			return Scalar{}, err
		}
		if IsTruthy(test) {
			return ev.eval(n.kids[1])
		}
		return ev.eval(n.kids[2])
	case kCall:
		fn := n.kids[0]
		args := n.kids[1:]
		if fn.kind == kName && !n.keywords {
			if fn.str == "_if" && len(args) == 3 {
				cond, err := ev.eval(args[0])
				if err != nil {
					return Scalar{}, err
				}
				if IsTruthy(cond) {
					return ev.eval(args[1])
				}
				return ev.eval(args[2])
			}
			if isFunction(fn.str) {
				return ev.callFunction(fn.str, args)
			}
		}
	}
	return Scalar{}, &ExprError{Msg: ev.notAllowed(n)}
}

func (ev *evaluator) divisionCheck(op string, b float64) error {
	if (op == "/" || op == "//" || op == "%") && b == 0 {
		return exprErr("Division durch 0 in '%s'", ev.source)
	}
	return nil
}

func isCompareOp(op string) bool {
	switch op {
	case "<", "<=", ">", ">=", "==", "!=":
		return true
	}
	return false
}

func compare(op string, a, b Scalar) bool {
	if a.IsText() {
		eq := a.text == b.text
		if op == "==" {
			return eq
		}
		return !eq
	}
	x, y := a.num, b.num
	switch op {
	case "<":
		return x < y
	case "<=":
		return x <= y
	case ">":
		return x > y
	case ">=":
		return x >= y
	case "==":
		return x == y
	}
	return x != y
}

// binary applies a float operator with CPython semantics (b != 0 for / // %).
func binary(op string, a, b float64) float64 {
	switch op {
	case "+":
		return a + b
	case "-":
		return a - b
	case "*":
		return a * b
	case "/":
		if b == 0 {
			return 0
		}
		return a / b
	case "//":
		if b == 0 {
			return 0
		}
		return pyFloorDiv(a, b)
	case "%":
		if b == 0 {
			return 0
		}
		return pyMod(a, b)
	}
	panic("expr: unknown operator " + op)
}

// pyMod is CPython's float_rem.
func pyMod(vx, wx float64) float64 {
	mod := math.Mod(vx, wx)
	if mod != 0 {
		if (wx < 0) != (mod < 0) {
			mod += wx
		}
	} else {
		mod = math.Copysign(0, wx)
	}
	return mod
}

// pyFloorDiv is CPython's float_floor_div (_float_div_mod).
func pyFloorDiv(vx, wx float64) float64 {
	mod := math.Mod(vx, wx)
	div := (vx - mod) / wx
	if mod != 0 {
		if (wx < 0) != (mod < 0) {
			div -= 1.0
		}
	}
	var floordiv float64
	if div != 0 {
		floordiv = math.Floor(div)
		if div-floordiv > 0.5 {
			floordiv += 1.0
		}
	} else {
		floordiv = math.Copysign(0, vx/wx)
	}
	return floordiv
}

// errBadCall stands for the TypeError/ValueError that Python turns into "Ungültiger Aufruf".
type errBadCall struct{}

func (errBadCall) Error() string { return "bad call" }

func (ev *evaluator) callFunction(name string, argNodes []*node) (Scalar, error) {
	bad := func() (Scalar, error) {
		return Scalar{}, exprErr("Ungültiger Aufruf von %s() in '%s'", name, ev.source)
	}
	args := make([]float64, len(argNodes))
	for i, a := range argNodes {
		x, err := ev.evalNumber(a)
		if err != nil {
			// ExprError is a ValueError in Python and caught by the call's except clause.
			if _, ok := err.(*ExprError); ok {
				return bad()
			}
			return Scalar{}, err
		}
		args[i] = x
	}
	r, err := applyFunction(name, args)
	if err != nil {
		if _, ok := err.(errBadCall); ok {
			return bad()
		}
		return Scalar{}, err
	}
	return Number(r), nil
}

func degToRad() float64 {
	pi := math.Pi
	return pi / 180.0
}

// applyFunction runs a whitelisted function like the Python lambdas and math functions.
func applyFunction(name string, args []float64) (float64, error) {
	one := func() (float64, error) {
		if len(args) != 1 {
			return 0, errBadCall{}
		}
		return args[0], nil
	}
	switch name {
	case "min", "max":
		if len(args) < 2 {
			// min() and min(x) raise TypeError (a float is not iterable).
			return 0, errBadCall{}
		}
		best := args[0]
		for _, x := range args[1:] {
			if (name == "min" && x < best) || (name == "max" && x > best) {
				best = x
			}
		}
		return best, nil
	case "abs":
		x, err := one()
		return math.Abs(x), err
	case "round":
		if len(args) < 1 || len(args) > 2 {
			return 0, errBadCall{}
		}
		n := 0.0
		if len(args) == 2 {
			n = args[1]
		}
		switch {
		case math.IsNaN(n):
			return 0, errBadCall{}
		case math.IsInf(n, 0):
			return 0, &OverflowError{Msg: "cannot convert float infinity to integer"}
		}
		return roundDigits(args[0], math.Trunc(n))
	case "floor", "ceil":
		x, err := one()
		if err != nil {
			return 0, err
		}
		switch {
		case math.IsNaN(x):
			return 0, errBadCall{}
		case math.IsInf(x, 0):
			return 0, &OverflowError{Msg: "cannot convert float infinity to integer"}
		}
		var r float64
		if name == "floor" {
			r = math.Floor(x)
		} else {
			r = math.Ceil(x)
		}
		// Python returns an int, which float() turns into +0.0 for a negative zero.
		return r + 0, nil
	case "sqrt":
		x, err := one()
		if err != nil {
			return 0, err
		}
		if x < 0 {
			return 0, errBadCall{}
		}
		return math.Sqrt(x), nil
	case "sin", "cos", "tan":
		x, err := one()
		if err != nil {
			return 0, err
		}
		r := x * degToRad()
		if math.IsInf(r, 0) {
			return 0, errBadCall{}
		}
		switch name {
		case "sin":
			return math.Sin(r), nil
		case "cos":
			return math.Cos(r), nil
		}
		return math.Tan(r), nil
	}
	return 0, errBadCall{}
}

func (ev *evaluator) names() []string { return ev.env.Names() }

// unknownName names the cause, the nearest declared name and the names that do exist.
func (ev *evaluator) unknownName(name string) string {
	message := fmt.Sprintf("Unbekannter Name '%s' in '%s'", name, ev.source)
	names := ev.names()
	for _, k := range names {
		if v, _ := ev.env.Get(k); v.IsText() && v.text == name {
			// A choice value written without quotes, e.g. "surface == boards".
			return fmt.Sprintf("%s – Auswahlwerte in Anführungszeichen schreiben: '%s'", message, name)
		}
	}
	closest, found := closeMatch(name, names)
	if !found {
		// Substring matches ("surface_type" vs "surface") that difflib scores too low.
		for _, k := range names {
			if utf8.RuneCountInString(k) > 2 && (strings.Contains(name, k) || strings.Contains(k, name)) {
				closest, found = k, true
				break
			}
		}
	}
	if found {
		message += fmt.Sprintf(" – meintest du '%s'?", closest)
	} else if isFunction(name) {
		message += fmt.Sprintf(" – %s ist eine Funktion und braucht Klammern: %s(...)", name, name)
	}
	listed := names
	more := ""
	if len(listed) > maxListedNames {
		listed = listed[:maxListedNames]
		more = " …"
	}
	return fmt.Sprintf("%s. Bekannte Namen: %s%s", message, strings.Join(listed, ", "), more)
}

// notAllowed says which construct is rejected and what to write instead.
func (ev *evaluator) notAllowed(n *node) string {
	base := fmt.Sprintf("Nicht erlaubter Ausdruck in '%s'", ev.source)
	switch n.kind {
	case kBinary:
		switch n.op {
		case "**":
			return base + ": Potenzen (**) gibt es nicht – als Produkt ausschreiben (x * x)"
		case "&", "|":
			return base + ": statt & und | bitte and bzw. or schreiben"
		}
	case kCall:
		fn := n.kids[0]
		if fn.kind == kName && fn.str == "_if" {
			return base + ": if braucht genau drei Argumente: if(Bedingung, dann, sonst)"
		}
		if fn.kind == kName && !n.keywords {
			hint := ""
			if closest, ok := closeMatch(fn.str, functionNames); ok {
				hint = fmt.Sprintf(" – meintest du %s()?", closest)
			}
			return fmt.Sprintf("%s: unbekannte Funktion %s()%s. Erlaubt: %s", base, fn.str, hint, allowed)
		}
		return base + ": Funktionen nehmen nur Positionsargumente, keine name=wert"
	case kAttribute, kSubscript, kList, kTuple, kDict:
		return base + ": Punkt, Index und Listen gibt es nicht. Erlaubt: " + allowed
	}
	return base + ". Erlaubt: " + allowed
}
