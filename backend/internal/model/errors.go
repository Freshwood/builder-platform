package model

import (
	"fmt"
	"strings"
)

// FieldError is one validation failure, shaped like an entry of pydantic's
// ValidationError.errors(): the location path, the message and the error type.
type FieldError struct {
	Loc  []string `json:"loc"`
	Msg  string   `json:"msg"`
	Type string   `json:"type"`
}

// Path joins the location with dots, e.g. "parts.0.size".
func (e FieldError) Path() string { return strings.Join(e.Loc, ".") }

// String renders "path: message" (only the message for model-level errors).
func (e FieldError) String() string {
	if len(e.Loc) == 0 {
		return e.Msg
	}
	return e.Path() + ": " + e.Msg
}

// ValidationError collects all field errors of one decode or Validate call.
type ValidationError struct {
	Errors []FieldError
}

// Error joins the errors as "path: message" lines separated by "; ".
func (e *ValidationError) Error() string {
	parts := make([]string, len(e.Errors))
	for i, fe := range e.Errors {
		parts[i] = fe.String()
	}
	if len(parts) == 1 {
		return parts[0]
	}
	return fmt.Sprintf("%d validation errors: %s", len(parts), strings.Join(parts, "; "))
}

// Messages renders each error like the agent's tool error texts:
// "path: message [type]".
func (e *ValidationError) Messages() []string {
	out := make([]string, len(e.Errors))
	for i, fe := range e.Errors {
		out[i] = fmt.Sprintf("%s: %s [%s]", fe.Path(), fe.Msg, fe.Type)
	}
	return out
}

// errList accumulates field errors during decoding and validation.
type errList struct {
	errs []FieldError
}

func (l *errList) add(loc []string, typ, msg string) {
	l.errs = append(l.errs, FieldError{Loc: append([]string(nil), loc...), Msg: msg, Type: typ})
}

func (l *errList) err() error {
	if len(l.errs) == 0 {
		return nil
	}
	return &ValidationError{Errors: l.errs}
}

func appendLoc(loc []string, part string) []string {
	out := make([]string, len(loc)+1)
	copy(out, loc)
	out[len(loc)] = part
	return out
}

// quoteChoices renders "'a', 'b' or 'c'" as pydantic does in literal and enum errors.
func quoteChoices(values []string) string {
	q := make([]string, len(values))
	for i, v := range values {
		q[i] = "'" + v + "'"
	}
	if len(q) == 1 {
		return q[0]
	}
	return strings.Join(q[:len(q)-1], ", ") + " or " + q[len(q)-1]
}

func plural(n int, word string) string {
	if n == 1 {
		return word
	}
	return word + "s"
}
