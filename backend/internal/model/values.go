package model

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"math"
	"reflect"
	"strconv"
	"strings"
	"time"
)

// ParamValueKind tells which Python type a ParamValue holds.
type ParamValueKind uint8

// Kinds of a ParamValue (Python int, float, str, bool).
const (
	IntKind ParamValueKind = iota
	FloatKind
	StringKind
	BoolKind
)

// ParamValue is Python's “int | float | str | bool“ union. It remembers which of the four
// types it holds, so 3 and 3.0 round-trip as they came in. The zero value is the int 0.
type ParamValue struct {
	kind ParamValueKind
	i    int64
	f    float64
	s    string
}

// IntValue returns an int ParamValue.
func IntValue(i int64) ParamValue { return ParamValue{kind: IntKind, i: i} }

// FloatValue returns a float ParamValue.
func FloatValue(f float64) ParamValue { return ParamValue{kind: FloatKind, f: f} }

// StringValue returns a str ParamValue.
func StringValue(s string) ParamValue { return ParamValue{kind: StringKind, s: s} }

// BoolValue returns a bool ParamValue.
func BoolValue(b bool) ParamValue {
	v := ParamValue{kind: BoolKind}
	if b {
		v.i = 1
	}
	return v
}

// Kind returns the Python type held.
func (v ParamValue) Kind() ParamValueKind { return v.kind }

// IsNumber reports int or float (bool does not count, as in “isinstance(v, bool)“ checks).
func (v ParamValue) IsNumber() bool { return v.kind == IntKind || v.kind == FloatKind }

// Int returns the int value and whether the value is an int.
func (v ParamValue) Int() (int64, bool) { return v.i, v.kind == IntKind }

// Float returns the numeric value of an int, float or bool (Python float(v)) and whether it is
// numeric at all.
func (v ParamValue) Float() (float64, bool) {
	switch v.kind {
	case IntKind, BoolKind:
		return float64(v.i), true
	case FloatKind:
		return v.f, true
	}
	return 0, false
}

// Str returns the string value and whether the value is a str.
func (v ParamValue) Str() (string, bool) { return v.s, v.kind == StringKind }

// Bool returns the bool value and whether the value is a bool.
func (v ParamValue) Bool() (bool, bool) { return v.i != 0, v.kind == BoolKind }

// PyStr renders the value like Python's str(): "3", "3.0", "True", "oak".
func (v ParamValue) PyStr() string {
	switch v.kind {
	case IntKind:
		return strconv.FormatInt(v.i, 10)
	case FloatKind:
		return FormatFloat(v.f)
	case BoolKind:
		if v.i != 0 {
			return "True"
		}
		return "False"
	}
	return v.s
}

// String implements fmt.Stringer (same as PyStr).
func (v ParamValue) String() string { return v.PyStr() }

// Equal compares like Python ==: numbers (including bools) compare numerically, strings only
// with strings.
func (v ParamValue) Equal(o ParamValue) bool {
	if v.kind == StringKind || o.kind == StringKind {
		return v.kind == o.kind && v.s == o.s
	}
	if v.kind != FloatKind && o.kind != FloatKind {
		return v.i == o.i
	}
	a, _ := v.Float()
	b, _ := o.Float()
	return a == b
}

func (v ParamValue) appendJSON(e *encoder, buf []byte) []byte {
	switch v.kind {
	case IntKind:
		return strconv.AppendInt(buf, v.i, 10)
	case FloatKind:
		return appendFloat(buf, v.f)
	case BoolKind:
		return strconv.AppendBool(buf, v.i != 0)
	}
	return appendString(buf, v.s)
}

func (v *ParamValue) decodeNode(d *decoder, n *node, loc []string) {
	switch n.kind {
	case nBool:
		*v = BoolValue(n.b)
	case nString:
		*v = StringValue(n.s)
	case nNumber:
		if n.isIntLiteral() {
			if i, err := strconv.ParseInt(n.s, 10, 64); err == nil {
				*v = IntValue(i)
				return
			}
		}
		// Integers beyond int64 fall back to float (Python keeps an arbitrary-size int).
		f, _ := strconv.ParseFloat(n.s, 64)
		*v = FloatValue(f)
	default:
		d.errs.add(appendLoc(loc, "int"), "int_type", "Input should be a valid integer")
		d.errs.add(appendLoc(loc, "float"), "float_type", "Input should be a valid number")
		d.errs.add(appendLoc(loc, "str"), "string_type", "Input should be a valid string")
		d.errs.add(appendLoc(loc, "bool"), "bool_type", "Input should be a valid boolean")
	}
}

// Expr is Python's “float | str“: a number or an arithmetic expression over parameters.
// The zero value is the number 0.
type Expr struct {
	isStr bool
	num   float64
	str   string
}

// Num returns a numeric Expr.
func Num(f float64) Expr { return Expr{num: f} }

// Formula returns an expression Expr, e.g. Formula("width_mm - 36").
func Formula(s string) Expr { return Expr{isStr: true, str: s} }

// IsString reports whether the Expr is an expression string.
func (x Expr) IsString() bool { return x.isStr }

// Number returns the numeric value (0 for expression strings).
func (x Expr) Number() float64 { return x.num }

// Str returns the expression string ("" for numbers).
func (x Expr) Str() string { return x.str }

// String renders the Expr like Python str(): "18.0" or the expression text.
func (x Expr) String() string {
	if x.isStr {
		return x.str
	}
	return FormatFloat(x.num)
}

func (x Expr) appendJSON(e *encoder, buf []byte) []byte {
	if x.isStr {
		return appendString(buf, x.str)
	}
	return appendFloat(buf, x.num)
}

func (x *Expr) decodeNode(d *decoder, n *node, loc []string) {
	switch n.kind {
	case nString:
		*x = Formula(n.s)
	case nNumber:
		f, _ := strconv.ParseFloat(n.s, 64)
		*x = Num(f)
	case nBool:
		// Lax float validation turns a bool into 0.0 / 1.0.
		if n.b {
			*x = Num(1)
		} else {
			*x = Num(0)
		}
	default:
		d.errs.add(appendLoc(loc, "float"), "float_type", "Input should be a valid number")
		d.errs.add(appendLoc(loc, "str"), "string_type", "Input should be a valid string")
	}
}

// UUID is a 128-bit identifier, serialised lowercase with hyphens.
type UUID [16]byte

// NewUUID returns a random (version 4) UUID.
func NewUUID() UUID {
	var u UUID
	if _, err := rand.Read(u[:]); err != nil {
		panic(err)
	}
	u[6] = (u[6] & 0x0f) | 0x40
	u[8] = (u[8] & 0x3f) | 0x80
	return u
}

// ParseUUID accepts the forms Python's uuid.UUID accepts: with or without hyphens, braces or a
// "urn:uuid:" prefix, any case.
func ParseUUID(s string) (UUID, error) {
	var u UUID
	t := strings.TrimPrefix(strings.TrimPrefix(s, "urn:"), "uuid:")
	t = strings.Trim(t, "{}")
	if strings.Contains(t, "-") {
		groups := strings.Split(t, "-")
		want := []int{8, 4, 4, 4, 12}
		if len(groups) != 5 {
			return u, fmt.Errorf("invalid group count: expected 5, found %d", len(groups))
		}
		for i, g := range groups {
			if len(g) != want[i] {
				return u, fmt.Errorf("invalid group length in group %d: expected %d, found %d", i, want[i], len(g))
			}
		}
		t = strings.Join(groups, "")
	}
	if len(t) != 32 {
		return u, fmt.Errorf("invalid length: expected length 32 for simple format, found %d", len(t))
	}
	if _, err := hex.Decode(u[:], []byte(t)); err != nil {
		return u, fmt.Errorf("invalid character")
	}
	return u, nil
}

// MustParseUUID is ParseUUID that panics on error (for tests and constants).
func MustParseUUID(s string) UUID {
	u, err := ParseUUID(s)
	if err != nil {
		panic(err)
	}
	return u
}

// String renders the canonical form "6ba7b810-9dad-11d1-80b4-00c04fd430c8".
func (u UUID) String() string {
	h := hex.EncodeToString(u[:])
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

// IsZero reports the nil UUID.
func (u UUID) IsZero() bool { return u == UUID{} }

func (u UUID) appendJSON(e *encoder, buf []byte) []byte { return appendString(buf, u.String()) }

func (u *UUID) decodeNode(d *decoder, n *node, loc []string) {
	if n.kind != nString {
		d.errs.add(loc, "uuid_type", "UUID input should be a string, bytes or UUID object")
		return
	}
	parsed, err := ParseUUID(n.s)
	if err != nil {
		d.errs.add(loc, "uuid_parsing", "Input should be a valid UUID, "+err.Error())
		return
	}
	*u = parsed
}

// DateTime is a Python datetime: aware (with UTC offset) or naive. It serialises like pydantic:
// "2026-10-16T17:47:26.525012Z", microseconds only when non-zero, "Z" for UTC.
type DateTime struct {
	Time  time.Time
	Naive bool
}

// NewDateTime returns an aware DateTime truncated to microseconds.
func NewDateTime(t time.Time) DateTime { return DateTime{Time: t.Truncate(time.Microsecond)} }

// Now returns the current time in UTC (Python “datetime.now(UTC)“).
func Now() DateTime { return NewDateTime(time.Now().UTC()) }

// IsZero reports the zero time.
func (dt DateTime) IsZero() bool { return dt.Time.IsZero() }

// String renders the isoformat used in JSON.
func (dt DateTime) String() string {
	t := dt.Time
	s := fmt.Sprintf("%04d-%02d-%02dT%02d:%02d:%02d", t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), t.Second())
	if us := t.Nanosecond() / 1000; us != 0 {
		s += fmt.Sprintf(".%06d", us)
	}
	if dt.Naive {
		return s
	}
	_, off := t.Zone()
	if off == 0 {
		return s + "Z"
	}
	sign := "+"
	if off < 0 {
		sign, off = "-", -off
	}
	s += fmt.Sprintf("%s%02d:%02d", sign, off/3600, off%3600/60)
	if off%60 != 0 {
		s += fmt.Sprintf(":%02d", off%60)
	}
	return s
}

func (dt DateTime) appendJSON(e *encoder, buf []byte) []byte {
	return appendString(buf, dt.String())
}

// ParseDateTime parses ISO 8601 date-times as pydantic does: "YYYY-MM-DD", optional "T" or " "
// and time "HH:MM[:SS[.ffffff]]", optional "Z" or "±HH[:MM]" offset. Fractions beyond
// microseconds are truncated. Without an offset the result is naive.
func ParseDateTime(s string) (DateTime, error) {
	bad := func(msg string) (DateTime, error) { return DateTime{}, fmt.Errorf("%s", msg) }
	num := func(str string) (int, bool) {
		if str == "" {
			return 0, false
		}
		for _, c := range str {
			if c < '0' || c > '9' {
				return 0, false
			}
		}
		v, err := strconv.Atoi(str)
		return v, err == nil
	}
	if len(s) < 10 {
		return bad("input is too short")
	}
	year, ok1 := num(s[0:4])
	month, ok2 := num(s[5:7])
	day, ok3 := num(s[8:10])
	if !ok1 || !ok2 || !ok3 || s[4] != '-' || s[7] != '-' {
		return bad("invalid date separator")
	}
	if month < 1 || month > 12 || day < 1 || day > 31 {
		return bad("day value is outside expected range")
	}
	rest := s[10:]
	hour, minute, sec, nsec := 0, 0, 0, 0
	loc := time.UTC
	naive := true
	if rest != "" {
		if rest[0] != 'T' && rest[0] != 't' && rest[0] != ' ' && rest[0] != '_' {
			return bad("unexpected extra characters at the end of the input")
		}
		rest = rest[1:]
		if len(rest) < 5 || rest[2] != ':' {
			return bad("invalid time separator")
		}
		var ok bool
		if hour, ok = num(rest[0:2]); !ok {
			return bad("invalid character in hour")
		}
		if minute, ok = num(rest[3:5]); !ok {
			return bad("invalid character in minute")
		}
		rest = rest[5:]
		if len(rest) >= 3 && rest[0] == ':' {
			if sec, ok = num(rest[1:3]); !ok {
				return bad("invalid character in second")
			}
			rest = rest[3:]
			if len(rest) > 0 && (rest[0] == '.' || rest[0] == ',') {
				j := 1
				for j < len(rest) && rest[j] >= '0' && rest[j] <= '9' {
					j++
				}
				frac := rest[1:j]
				if frac == "" {
					return bad("second fraction value is missing")
				}
				if len(frac) > 6 {
					frac = frac[:6]
				}
				frac += strings.Repeat("0", 6-len(frac))
				us, _ := strconv.Atoi(frac)
				nsec = us * 1000
				rest = rest[j:]
			}
		}
		if hour > 23 || minute > 59 || sec > 59 {
			return bad("time value is outside expected range")
		}
		if rest != "" {
			naive = false
			if rest == "Z" || rest == "z" {
				loc = time.UTC
			} else {
				sign := 1
				switch rest[0] {
				case '+':
				case '-':
					sign = -1
				default:
					return bad("invalid timezone sign")
				}
				tz := strings.ReplaceAll(rest[1:], ":", "")
				if len(tz) != 2 && len(tz) != 4 {
					return bad("invalid timezone hour or minute")
				}
				th, ok1 := num(tz[0:2])
				tm := 0
				ok2 := true
				if len(tz) == 4 {
					tm, ok2 = num(tz[2:4])
				}
				if !ok1 || !ok2 {
					return bad("invalid timezone hour or minute")
				}
				off := sign * (th*3600 + tm*60)
				if off == 0 {
					loc = time.UTC
				} else {
					loc = time.FixedZone("", off)
				}
			}
		}
	}
	t := time.Date(year, time.Month(month), day, hour, minute, sec, nsec, loc)
	if t.Day() != day {
		return bad("day value is outside expected range")
	}
	return DateTime{Time: t, Naive: naive}, nil
}

func (dt *DateTime) decodeNode(d *decoder, n *node, loc []string) {
	switch n.kind {
	case nString:
		parsed, err := ParseDateTime(n.s)
		if err != nil {
			typ := "datetime_parsing"
			msg := "Input should be a valid datetime, " + err.Error()
			if len(n.s) < 10 || (len(n.s) == 10) {
				typ = "datetime_from_date_parsing"
				msg = "Input should be a valid datetime or date, " + err.Error()
			}
			d.errs.add(loc, typ, msg)
			return
		}
		*dt = parsed
	case nNumber:
		f, err := strconv.ParseFloat(n.s, 64)
		if err != nil || math.IsInf(f, 0) || math.IsNaN(f) {
			d.errs.add(loc, "datetime_parsing", "Input should be a valid datetime")
			return
		}
		// pydantic treats values above 2e10 as milliseconds.
		if math.Abs(f) > 2e10 {
			f /= 1000
		}
		secs := math.Floor(f)
		us := math.Round((f - secs) * 1e6)
		*dt = DateTime{Time: time.Unix(int64(secs), int64(us)*1000).UTC()}
	default:
		d.errs.add(loc, "datetime_type", "Input should be a valid datetime")
	}
}

// Dict is an insertion-ordered map with string keys, the Go counterpart of a Python dict. The
// zero value is an empty dict ready to use. Setting an existing key keeps its position.
type Dict[V any] struct {
	keys []string
	m    map[string]V
}

// NewDict builds a Dict from alternating keys and values given as pairs.
func NewDict[V any](pairs ...DictEntry[V]) Dict[V] {
	var d Dict[V]
	for _, p := range pairs {
		d.Set(p.Key, p.Value)
	}
	return d
}

// DictEntry is one key/value pair of a Dict.
type DictEntry[V any] struct {
	Key   string
	Value V
}

// Len returns the number of entries.
func (d Dict[V]) Len() int { return len(d.keys) }

// Get returns the value for key and whether it exists.
func (d Dict[V]) Get(key string) (V, bool) {
	v, ok := d.m[key]
	return v, ok
}

// Has reports whether key exists.
func (d Dict[V]) Has(key string) bool {
	_, ok := d.m[key]
	return ok
}

// Set inserts or replaces a value; new keys go to the end.
func (d *Dict[V]) Set(key string, v V) {
	if d.m == nil {
		d.m = map[string]V{}
	}
	if _, ok := d.m[key]; !ok {
		d.keys = append(d.keys, key)
	}
	d.m[key] = v
}

// Delete removes key if present.
func (d *Dict[V]) Delete(key string) {
	if _, ok := d.m[key]; !ok {
		return
	}
	delete(d.m, key)
	for i, k := range d.keys {
		if k == key {
			d.keys = append(d.keys[:i:i], d.keys[i+1:]...)
			break
		}
	}
}

// Keys returns the keys in insertion order (a copy).
func (d Dict[V]) Keys() []string { return append([]string(nil), d.keys...) }

// Entries returns the entries in insertion order.
func (d Dict[V]) Entries() []DictEntry[V] {
	out := make([]DictEntry[V], len(d.keys))
	for i, k := range d.keys {
		out[i] = DictEntry[V]{Key: k, Value: d.m[k]}
	}
	return out
}

// All iterates over the entries in insertion order.
func (d Dict[V]) All() func(yield func(string, V) bool) {
	return func(yield func(string, V) bool) {
		for _, k := range d.keys {
			if !yield(k, d.m[k]) {
				return
			}
		}
	}
}

// Clone returns a shallow copy that can be modified independently.
func (d Dict[V]) Clone() Dict[V] {
	out := Dict[V]{keys: append([]string(nil), d.keys...), m: make(map[string]V, len(d.m))}
	for k, v := range d.m {
		out.m[k] = v
	}
	return out
}

// Merge returns a copy updated with other, like Python “{**d, **other}“.
func (d Dict[V]) Merge(other Dict[V]) Dict[V] {
	out := d.Clone()
	for _, k := range other.keys {
		out.Set(k, other.m[k])
	}
	return out
}

// Map returns the entries as a plain Go map (order is lost).
func (d Dict[V]) Map() map[string]V {
	out := make(map[string]V, len(d.m))
	for k, v := range d.m {
		out[k] = v
	}
	return out
}

func (d Dict[V]) appendJSON(e *encoder, buf []byte) []byte {
	buf = append(buf, '{')
	for i, k := range d.keys {
		if i > 0 {
			buf = append(buf, ',')
		}
		buf = appendString(buf, k)
		buf = append(buf, ':')
		v := d.m[k]
		buf = e.encode(buf, reflect.ValueOf(&v).Elem())
	}
	return append(buf, '}')
}

func (d *Dict[V]) decodeNode(dec *decoder, n *node, loc []string) {
	if n.kind != nObject {
		dec.errs.add(loc, "dict_type", "Input should be an object")
		return
	}
	*d = Dict[V]{}
	for i, k := range n.keys {
		var v V
		dec.decode(n.vals[i], reflect.ValueOf(&v).Elem(), appendLoc(loc, k))
		d.Set(k, v)
	}
}

func (d Dict[V]) walkValues(w *walker, loc []string) {
	for _, k := range d.keys {
		v := d.m[k]
		w.walk(reflect.ValueOf(&v).Elem(), appendLoc(loc, k))
	}
}
