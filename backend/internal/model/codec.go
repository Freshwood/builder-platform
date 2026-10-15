package model

import (
	"encoding/json"
	"fmt"
	"math"
	"math/big"
	"reflect"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"unicode/utf8"

	"github.com/shopspring/decimal"
)

// This file implements a small, reflection based counterpart of pydantic for the model types:
//
//   - Decode parses JSON with pydantic's lax coercions (e.g. "18" or 18.0 for an int field),
//     fills defaults for missing fields, rejects unknown fields and validates constraints.
//   - Encode writes JSON like model_dump(mode="json"): every field, nulls included, decimals as
//     Python strings, floats in Python repr, union members with their tag.
//
// Struct fields are described with tags:
//
//	json:"name"            JSON field name (required).
//	def:"<json>"           Default when the field is missing; without it the field is required.
//	                       "uuid4" and "now" generate a random UUID / the current UTC time.
//	v:"rule,rule"          Constraints: minlen=N, maxlen=N, pattern=<name> (strings or each
//	                       element of a []string), minitems=N, maxitems=N (lists, dicts),
//	                       ge=X, le=X (numbers and decimals), places=N (decimal places),
//	                       const=X (int literal).
//
// String types implementing `pyChoices() ([]string, bool)` are Literal (false) or StrEnum
// (true) types. Structs with a method `validateModel() error` get it called after their fields
// validated, like a pydantic model_validator(mode="after"). Structs with `allowExtra()` ignore
// unknown fields instead of rejecting them.

// Patterns usable in the v:"pattern=..." tag.
var patterns = map[string]string{
	"ident":  `^[a-z][a-z0-9_]{0,39}$`,
	"choice": `^[a-z0-9_]{1,40}$`,
}

var compiledPatterns = func() map[string]*regexp.Regexp {
	out := map[string]*regexp.Regexp{}
	for k, p := range patterns {
		out[k] = regexp.MustCompile(p)
	}
	return out
}()

type choicer interface {
	pyChoices() (values []string, isEnum bool)
}

type modelValidator interface {
	validateModel() error
}

type extraAllower interface {
	allowExtra()
}

// unionMember is implemented by the members of a discriminated union.
type unionMember interface {
	unionTag() (field, tag string)
}

type nodeDecoder interface {
	decodeNode(d *decoder, n *node, loc []string)
}

type jsonAppender interface {
	appendJSON(e *encoder, buf []byte) []byte
}

type valueWalker interface {
	walkValues(w *walker, loc []string)
}

type unionSpec struct {
	field   string
	tags    []string
	members map[string]reflect.Type
}

var unions = map[reflect.Type]*unionSpec{}

func registerUnion[I any](field string, members ...unionMember) {
	spec := &unionSpec{field: field, members: map[string]reflect.Type{}}
	for _, m := range members {
		_, tag := m.unionTag()
		spec.tags = append(spec.tags, tag)
		spec.members[tag] = reflect.TypeOf(m)
	}
	unions[reflect.TypeFor[I]()] = spec
}

type constraints struct {
	minLen, maxLen     int
	hasMinLen, hasMax  bool
	pattern            string
	minItems, maxItems int
	hasMinIt, hasMaxIt bool
	ge, le             string
	places             int
	hasPlaces          bool
	constVal           string
}

type fieldInfo struct {
	index  int
	name   string
	def    string
	hasDef bool
	cons   constraints
}

type structInfo struct {
	fields     []fieldInfo
	byName     map[string]int
	allowExtra bool
	tagField   string
	tagValue   string
	validator  bool
}

var structCache sync.Map

func getStructInfo(t reflect.Type) *structInfo {
	if v, ok := structCache.Load(t); ok {
		return v.(*structInfo)
	}
	info := &structInfo{byName: map[string]int{}}
	for i := 0; i < t.NumField(); i++ {
		sf := t.Field(i)
		if !sf.IsExported() {
			continue
		}
		name := strings.Split(sf.Tag.Get("json"), ",")[0]
		if name == "" || name == "-" {
			continue
		}
		fi := fieldInfo{index: i, name: name}
		fi.def, fi.hasDef = sf.Tag.Lookup("def")
		if v := sf.Tag.Get("v"); v != "" {
			fi.cons = parseConstraints(v)
		}
		info.byName[name] = len(info.fields)
		info.fields = append(info.fields, fi)
	}
	zero := reflect.Zero(t).Interface()
	if _, ok := zero.(extraAllower); ok {
		info.allowExtra = true
	}
	if m, ok := zero.(unionMember); ok {
		info.tagField, info.tagValue = m.unionTag()
	}
	if _, ok := zero.(modelValidator); ok {
		info.validator = true
	}
	structCache.Store(t, info)
	return info
}

func parseConstraints(tag string) constraints {
	var c constraints
	for _, part := range strings.Split(tag, ",") {
		key, val, _ := strings.Cut(part, "=")
		n, _ := strconv.Atoi(val)
		switch key {
		case "minlen":
			c.minLen, c.hasMinLen = n, true
		case "maxlen":
			c.maxLen, c.hasMax = n, true
		case "pattern":
			if _, ok := patterns[val]; !ok {
				panic("model: unknown pattern " + val)
			}
			c.pattern = val
		case "minitems":
			c.minItems, c.hasMinIt = n, true
		case "maxitems":
			c.maxItems, c.hasMaxIt = n, true
		case "ge":
			c.ge = val
		case "le":
			c.le = val
		case "places":
			c.places, c.hasPlaces = n, true
		case "const":
			c.constVal = val
		default:
			panic("model: unknown constraint " + key)
		}
	}
	return c
}

var decimalType = reflect.TypeFor[decimal.Decimal]()

// ---------------------------------------------------------------------------------------------
// Decoding

type decoder struct {
	errs         errList
	skipRequired bool
}

// Decode parses JSON into v (a non-nil pointer) with pydantic's coercion rules, applies
// defaults, and validates all constraints and model validators. Errors are returned as
// *ValidationError with pydantic-style locations, messages and types.
func Decode(data []byte, v any) error {
	rv := reflect.ValueOf(v)
	if rv.Kind() != reflect.Pointer || rv.IsNil() {
		return fmt.Errorf("model.Decode: need a non-nil pointer, got %T", v)
	}
	n, err := parseNode(data)
	if err != nil {
		return &ValidationError{Errors: []FieldError{{Msg: "Invalid JSON: " + err.Error(), Type: "json_invalid"}}}
	}
	d := &decoder{}
	target := reflect.New(rv.Elem().Type()).Elem()
	d.decode(n, target, nil)
	if err := d.errs.err(); err != nil {
		return err
	}
	if err := validateValue(target); err != nil {
		return err
	}
	rv.Elem().Set(target)
	return nil
}

// New returns a T with all field defaults applied (as pydantic would for missing fields);
// required fields keep their Go zero values.
func New[T any]() T {
	var out T
	d := &decoder{skipRequired: true}
	d.decode(&node{kind: nObject}, reflect.ValueOf(&out).Elem(), nil)
	return out
}

var defaultNodes sync.Map

func defaultNode(lit string) *node {
	if v, ok := defaultNodes.Load(lit); ok {
		return v.(*node)
	}
	n, err := parseNode([]byte(lit))
	if err != nil {
		panic("model: invalid default " + lit)
	}
	defaultNodes.Store(lit, n)
	return n
}

func (d *decoder) decode(n *node, v reflect.Value, loc []string) {
	if v.CanAddr() {
		if nd, ok := v.Addr().Interface().(nodeDecoder); ok {
			nd.decodeNode(d, n, loc)
			return
		}
	}
	t := v.Type()
	if t == decimalType {
		d.decodeDecimal(n, v, loc)
		return
	}
	if spec, ok := unions[t]; ok {
		d.decodeUnion(spec, n, v, loc)
		return
	}
	switch t.Kind() {
	case reflect.Pointer:
		if n.kind == nNull {
			v.Set(reflect.Zero(t))
			return
		}
		p := reflect.New(t.Elem())
		d.decode(n, p.Elem(), loc)
		v.Set(p)
	case reflect.Struct:
		d.decodeStruct(n, v, loc)
	case reflect.Slice:
		if n.kind != nArray {
			d.errs.add(loc, "list_type", "Input should be a valid array")
			return
		}
		s := reflect.MakeSlice(t, len(n.arr), len(n.arr))
		for i, child := range n.arr {
			d.decode(child, s.Index(i), appendLoc(loc, strconv.Itoa(i)))
		}
		v.Set(s)
	case reflect.Array:
		if n.kind != nArray {
			d.errs.add(loc, "tuple_type", "Input should be a valid array")
			return
		}
		size := t.Len()
		if len(n.arr) > size {
			d.errs.add(loc, "too_long", fmt.Sprintf("Tuple should have at most %d %s after validation, not %d", size, plural(size, "item"), len(n.arr)))
			return
		}
		for i := 0; i < size; i++ {
			l := appendLoc(loc, strconv.Itoa(i))
			if i >= len(n.arr) {
				d.errs.add(l, "missing", "Field required")
				continue
			}
			d.decode(n.arr[i], v.Index(i), l)
		}
	case reflect.String:
		d.decodeString(n, v, loc)
	case reflect.Int, reflect.Int64, reflect.Int32:
		d.decodeInt(n, v, loc)
	case reflect.Float64, reflect.Float32:
		d.decodeFloat(n, v, loc)
	case reflect.Bool:
		d.decodeBool(n, v, loc)
	default:
		panic("model: unsupported type " + t.String())
	}
}

func (d *decoder) decodeStruct(n *node, v reflect.Value, loc []string) {
	info := getStructInfo(v.Type())
	if n.kind != nObject {
		d.errs.add(loc, "model_type", "Input should be an object")
		return
	}
	seen := make([]bool, len(info.fields))
	for i, key := range n.keys {
		val := n.vals[i]
		if info.tagField != "" && key == info.tagField {
			if val.kind != nString || val.s != info.tagValue {
				d.errs.add(appendLoc(loc, key), "literal_error", "Input should be "+quoteChoices([]string{info.tagValue}))
			}
			continue
		}
		idx, ok := info.byName[key]
		if !ok {
			if !info.allowExtra {
				d.errs.add(appendLoc(loc, key), "extra_forbidden", "Extra inputs are not permitted")
			}
			continue
		}
		seen[idx] = true
		f := info.fields[idx]
		d.decode(val, v.Field(f.index), appendLoc(loc, key))
	}
	for idx, f := range info.fields {
		if seen[idx] {
			continue
		}
		field := v.Field(f.index)
		switch {
		case f.hasDef && f.def == "uuid4":
			field.Set(reflect.ValueOf(NewUUID()))
		case f.hasDef && f.def == "now":
			field.Set(reflect.ValueOf(Now()))
		case f.hasDef:
			d.decode(defaultNode(f.def), field, appendLoc(loc, f.name))
		case !d.skipRequired:
			d.errs.add(appendLoc(loc, f.name), "missing", "Field required")
		}
	}
}

func (d *decoder) decodeUnion(spec *unionSpec, n *node, v reflect.Value, loc []string) {
	if n.kind != nObject {
		d.errs.add(loc, "dict_type", "Input should be an object")
		return
	}
	tagNode, ok := n.get(spec.field)
	if !ok {
		d.errs.add(loc, "union_tag_not_found", fmt.Sprintf("Unable to extract tag using discriminator '%s'", spec.field))
		return
	}
	tag := tagNode.s
	mt, ok := spec.members[tag]
	if tagNode.kind != nString || !ok {
		d.errs.add(loc, "union_tag_invalid", fmt.Sprintf(
			"Input tag '%s' found using '%s' does not match any of the expected tags: %s",
			tag, spec.field, "'"+strings.Join(spec.tags, "', '")+"'"))
		return
	}
	member := reflect.New(mt).Elem()
	d.decode(n, member, appendLoc(loc, tag))
	v.Set(member)
}

func (d *decoder) decodeString(n *node, v reflect.Value, loc []string) {
	if n.kind != nString {
		d.errs.add(loc, "string_type", "Input should be a valid string")
		return
	}
	if c, ok := reflect.Zero(v.Type()).Interface().(choicer); ok {
		values, isEnum := c.pyChoices()
		if !contains(values, n.s) {
			typ := "literal_error"
			if isEnum {
				typ = "enum"
			}
			d.errs.add(loc, typ, "Input should be "+quoteChoices(values))
			return
		}
	}
	v.SetString(n.s)
}

func contains(values []string, s string) bool {
	for _, v := range values {
		if v == s {
			return true
		}
	}
	return false
}

func (d *decoder) decodeInt(n *node, v reflect.Value, loc []string) {
	switch n.kind {
	case nBool:
		if n.b {
			v.SetInt(1)
		} else {
			v.SetInt(0)
		}
	case nNumber:
		if n.isIntLiteral() {
			i, err := strconv.ParseInt(n.s, 10, 64)
			if err != nil {
				d.errs.add(loc, "int_parsing_size", "Unable to parse input string as an integer, exceeded maximum size")
				return
			}
			v.SetInt(i)
			return
		}
		f, err := strconv.ParseFloat(n.s, 64)
		if err != nil || math.IsInf(f, 0) {
			d.errs.add(loc, "finite_number", "Input should be a finite number")
			return
		}
		d.setIntFromFloat(f, v, loc)
	case nString:
		s := strings.TrimSpace(n.s)
		if i, err := strconv.ParseInt(s, 10, 64); err == nil {
			v.SetInt(i)
			return
		}
		d.errs.add(loc, "int_parsing", "Input should be a valid integer, unable to parse string as an integer")
	default:
		d.errs.add(loc, "int_type", "Input should be a valid integer")
	}
}

func (d *decoder) setIntFromFloat(f float64, v reflect.Value, loc []string) {
	if f != math.Trunc(f) {
		d.errs.add(loc, "int_from_float", "Input should be a valid integer, got a number with a fractional part")
		return
	}
	if f >= 9.223372036854775807e18 || f < -9.223372036854775808e18 {
		d.errs.add(loc, "int_parsing_size", "Unable to parse input string as an integer, exceeded maximum size")
		return
	}
	v.SetInt(int64(f))
}

func (d *decoder) decodeFloat(n *node, v reflect.Value, loc []string) {
	switch n.kind {
	case nBool:
		if n.b {
			v.SetFloat(1)
		} else {
			v.SetFloat(0)
		}
	case nNumber:
		f, _ := strconv.ParseFloat(n.s, 64)
		v.SetFloat(f)
	case nString:
		s := strings.TrimSpace(n.s)
		f, err := strconv.ParseFloat(s, 64)
		if err != nil && !isRangeErr(err) {
			d.errs.add(loc, "float_parsing", "Input should be a valid number, unable to parse string as a number")
			return
		}
		v.SetFloat(f)
	default:
		d.errs.add(loc, "float_type", "Input should be a valid number")
	}
}

func isRangeErr(err error) bool {
	ne, ok := err.(*strconv.NumError)
	return ok && ne.Err == strconv.ErrRange
}

func (d *decoder) decodeBool(n *node, v reflect.Value, loc []string) {
	const parsing = "Input should be a valid boolean, unable to interpret input"
	switch n.kind {
	case nBool:
		v.SetBool(n.b)
	case nNumber:
		f, err := strconv.ParseFloat(n.s, 64)
		switch {
		case err == nil && f == 0:
			v.SetBool(false)
		case err == nil && f == 1:
			v.SetBool(true)
		default:
			d.errs.add(loc, "bool_parsing", parsing)
		}
	case nString:
		switch strings.ToLower(n.s) {
		case "0", "off", "f", "false", "n", "no":
			v.SetBool(false)
		case "1", "on", "t", "true", "y", "yes":
			v.SetBool(true)
		default:
			d.errs.add(loc, "bool_parsing", parsing)
		}
	default:
		d.errs.add(loc, "bool_type", "Input should be a valid boolean")
	}
}

func (d *decoder) decodeDecimal(n *node, v reflect.Value, loc []string) {
	var (
		val decimal.Decimal
		err error
	)
	switch n.kind {
	case nNumber:
		if n.isIntLiteral() {
			val, err = decimal.NewFromString(n.s)
		} else {
			f, ferr := strconv.ParseFloat(n.s, 64)
			if ferr != nil || math.IsInf(f, 0) {
				d.errs.add(loc, "finite_number", "Input should be a finite number")
				return
			}
			val = DecimalFromFloat(f)
		}
	case nString:
		s := strings.ToLower(strings.TrimLeft(strings.TrimSpace(n.s), "+-"))
		if s == "nan" || s == "snan" || s == "inf" || s == "infinity" {
			d.errs.add(loc, "finite_number", "Input should be a finite number")
			return
		}
		val, err = ParseDecimal(n.s)
	default:
		d.errs.add(loc, "decimal_type", "Decimal input should be an integer, float, string or Decimal object")
		return
	}
	if err != nil {
		d.errs.add(loc, "decimal_parsing", "Input should be a valid decimal")
		return
	}
	v.Set(reflect.ValueOf(val))
}

// ---------------------------------------------------------------------------------------------
// Validation (constraints and model validators on Go values)

type walker struct {
	errs errList
}

// Validate checks the constraints and model validators of v (a model value or pointer to one),
// as pydantic does when constructing the model. It returns a *ValidationError or nil.
func Validate(v any) error {
	return validateValue(reflect.ValueOf(v))
}

func validateValue(v reflect.Value) error {
	w := &walker{}
	w.walk(v, nil)
	return w.errs.err()
}

// walk validates v recursively and reports whether it added errors.
func (w *walker) walk(v reflect.Value, loc []string) bool {
	before := len(w.errs.errs)
	t := v.Type()
	if k := t.Kind(); k != reflect.Pointer && k != reflect.Interface {
		if vw, ok := v.Interface().(valueWalker); ok {
			vw.walkValues(w, loc)
			return len(w.errs.errs) > before
		}
	}
	if spec, ok := unions[t]; ok {
		if v.IsNil() {
			w.errs.add(loc, "union_tag_not_found", fmt.Sprintf("Unable to extract tag using discriminator '%s'", spec.field))
			return true
		}
		inner := v.Elem()
		if m, ok := inner.Interface().(unionMember); ok {
			_, tag := m.unionTag()
			w.walk(inner, appendLoc(loc, tag))
		}
		return len(w.errs.errs) > before
	}
	if t == decimalType {
		return false
	}
	switch t.Kind() {
	case reflect.Pointer, reflect.Interface:
		if !v.IsNil() {
			w.walk(v.Elem(), loc)
		}
	case reflect.Struct:
		if _, ok := v.Interface().(jsonAppender); ok {
			return len(w.errs.errs) > before
		}
		info := getStructInfo(t)
		for _, f := range info.fields {
			fl := appendLoc(loc, f.name)
			fv := v.Field(f.index)
			w.checkConstraints(fv, f.cons, fl)
			w.walk(fv, fl)
		}
		if info.validator && len(w.errs.errs) == before {
			if err := v.Interface().(modelValidator).validateModel(); err != nil {
				w.errs.add(loc, "value_error", "Value error, "+err.Error())
			}
		}
	case reflect.Slice, reflect.Array:
		for i := 0; i < v.Len(); i++ {
			w.walk(v.Index(i), appendLoc(loc, strconv.Itoa(i)))
		}
	case reflect.String:
		if c, ok := v.Interface().(choicer); ok {
			values, isEnum := c.pyChoices()
			if !contains(values, v.String()) {
				typ := "literal_error"
				if isEnum {
					typ = "enum"
				}
				w.errs.add(loc, typ, "Input should be "+quoteChoices(values))
			}
		}
	}
	return len(w.errs.errs) > before
}

func (w *walker) checkConstraints(v reflect.Value, c constraints, loc []string) {
	if v.Kind() == reflect.Pointer {
		if v.IsNil() {
			return
		}
		v = v.Elem()
	}
	if c.hasMinIt || c.hasMaxIt {
		var n int
		what := "List"
		if lv, ok := v.Interface().(interface{ Len() int }); ok {
			n = lv.Len()
			what = "Dictionary"
		} else {
			n = v.Len()
		}
		if c.hasMinIt && n < c.minItems {
			w.errs.add(loc, "too_short", fmt.Sprintf("%s should have at least %d %s after validation, not %d", what, c.minItems, plural(c.minItems, "item"), n))
		}
		if c.hasMaxIt && n > c.maxItems {
			w.errs.add(loc, "too_long", fmt.Sprintf("%s should have at most %d %s after validation, not %d", what, c.maxItems, plural(c.maxItems, "item"), n))
		}
	}
	if v.Kind() == reflect.Slice && v.Type().Elem().Kind() == reflect.String {
		for i := 0; i < v.Len(); i++ {
			w.checkString(v.Index(i).String(), c, appendLoc(loc, strconv.Itoa(i)))
		}
		return
	}
	if v.Kind() == reflect.String {
		w.checkString(v.String(), c, loc)
		return
	}
	if c.ge == "" && c.le == "" && !c.hasPlaces && c.constVal == "" {
		return
	}
	var num decimal.Decimal
	switch {
	case v.Type() == decimalType:
		num = v.Interface().(decimal.Decimal)
	case v.CanInt():
		num = decimal.NewFromInt(v.Int())
	case v.CanFloat():
		num = decimal.NewFromFloat(v.Float())
	default:
		return
	}
	if c.constVal != "" {
		if num.String() != c.constVal {
			w.errs.add(loc, "literal_error", "Input should be "+c.constVal)
		}
		return
	}
	if c.ge != "" && num.LessThan(decimal.RequireFromString(c.ge)) {
		w.errs.add(loc, "greater_than_equal", "Input should be greater than or equal to "+c.ge)
		return
	}
	if c.le != "" && num.GreaterThan(decimal.RequireFromString(c.le)) {
		w.errs.add(loc, "less_than_equal", "Input should be less than or equal to "+c.le)
		return
	}
	if c.hasPlaces {
		// pydantic counts decimal places after normalising (1.230 has two).
		places := 0
		norm := normalizeDecimal(num)
		if e := int(norm.Exponent()); e < 0 {
			places = -e
		}
		if places > c.places {
			w.errs.add(loc, "decimal_max_places", fmt.Sprintf("Decimal input should have no more than %d %s", c.places, plural(c.places, "decimal place")))
		}
	}
}

func normalizeDecimal(d decimal.Decimal) decimal.Decimal {
	coef := d.Coefficient()
	exp := d.Exponent()
	if coef.Sign() == 0 {
		return decimal.New(0, 0)
	}
	ten := bigTen
	for {
		q, r := new(big.Int).QuoRem(coef, ten, new(big.Int))
		if r.Sign() != 0 {
			break
		}
		coef = q
		exp++
	}
	return decimal.NewFromBigInt(coef, exp)
}

func (w *walker) checkString(s string, c constraints, loc []string) {
	n := utf8.RuneCountInString(s)
	if c.hasMinLen && n < c.minLen {
		w.errs.add(loc, "string_too_short", fmt.Sprintf("String should have at least %d %s", c.minLen, plural(c.minLen, "character")))
	}
	if c.hasMax && n > c.maxLen {
		w.errs.add(loc, "string_too_long", fmt.Sprintf("String should have at most %d %s", c.maxLen, plural(c.maxLen, "character")))
	}
	if c.pattern != "" && !compiledPatterns[c.pattern].MatchString(s) {
		w.errs.add(loc, "string_pattern_mismatch", fmt.Sprintf("String should match pattern '%s'", patterns[c.pattern]))
	}
}

// ---------------------------------------------------------------------------------------------
// Encoding

type encoder struct{}

// Encode serialises v like pydantic's model_dump(mode="json") rendered as JSON.
func Encode(v any) ([]byte, error) {
	e := &encoder{}
	return e.encode(nil, reflect.ValueOf(v)), nil
}

func (e *encoder) encode(buf []byte, v reflect.Value) []byte {
	if !v.IsValid() {
		return append(buf, "null"...)
	}
	t := v.Type()
	if k := t.Kind(); k == reflect.Pointer || k == reflect.Interface {
		if v.IsNil() {
			return append(buf, "null"...)
		}
		return e.encode(buf, v.Elem())
	}
	if a, ok := v.Interface().(jsonAppender); ok {
		return a.appendJSON(e, buf)
	}
	if t == decimalType {
		return appendString(buf, FormatDecimal(v.Interface().(decimal.Decimal)))
	}
	switch t.Kind() {
	case reflect.Pointer, reflect.Interface:
		if v.IsNil() {
			return append(buf, "null"...)
		}
		return e.encode(buf, v.Elem())
	case reflect.Struct:
		info := getStructInfo(t)
		buf = append(buf, '{')
		first := true
		if info.tagField != "" {
			buf = appendString(buf, info.tagField)
			buf = append(buf, ':')
			buf = appendString(buf, info.tagValue)
			first = false
		}
		for _, f := range info.fields {
			if !first {
				buf = append(buf, ',')
			}
			first = false
			buf = appendString(buf, f.name)
			buf = append(buf, ':')
			buf = e.encode(buf, v.Field(f.index))
		}
		return append(buf, '}')
	case reflect.Slice, reflect.Array:
		buf = append(buf, '[')
		for i := 0; i < v.Len(); i++ {
			if i > 0 {
				buf = append(buf, ',')
			}
			buf = e.encode(buf, v.Index(i))
		}
		return append(buf, ']')
	case reflect.String:
		return appendString(buf, v.String())
	case reflect.Int, reflect.Int64, reflect.Int32, reflect.Int16, reflect.Int8:
		return strconv.AppendInt(buf, v.Int(), 10)
	case reflect.Float64, reflect.Float32:
		return appendFloat(buf, v.Float())
	case reflect.Bool:
		return strconv.AppendBool(buf, v.Bool())
	case reflect.Map:
		// Plain Go maps are written with sorted keys (encoding/json behaviour).
		b, err := json.Marshal(v.Interface())
		if err != nil {
			panic(err)
		}
		return append(buf, b...)
	}
	panic("model: cannot encode " + t.String())
}

func appendFloat(buf []byte, f float64) []byte {
	if math.IsInf(f, 0) || math.IsNaN(f) {
		return append(buf, "null"...)
	}
	return append(buf, FormatFloat(f)...)
}

func appendString(buf []byte, s string) []byte {
	const hexDigits = "0123456789abcdef"
	buf = append(buf, '"')
	for i := 0; i < len(s); {
		c := s[i]
		if c < utf8.RuneSelf {
			switch {
			case c == '"' || c == '\\':
				buf = append(buf, '\\', c)
			case c == '\n':
				buf = append(buf, '\\', 'n')
			case c == '\r':
				buf = append(buf, '\\', 'r')
			case c == '\t':
				buf = append(buf, '\\', 't')
			case c < 0x20:
				buf = append(buf, '\\', 'u', '0', '0', hexDigits[c>>4], hexDigits[c&0xf])
			default:
				buf = append(buf, c)
			}
			i++
			continue
		}
		r, size := utf8.DecodeRuneInString(s[i:])
		if r == utf8.RuneError && size == 1 {
			buf = append(buf, `\ufffd`...)
		} else {
			buf = append(buf, s[i:i+size]...)
		}
		i += size
	}
	return append(buf, '"')
}
