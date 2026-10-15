package agent

import (
	"regexp"
	"strings"
)

// Model routing (ADR-0006): pick the model for a chat turn deterministically, without an extra
// LLM call. Free-form designs stay on the designer model, and every new project is a design
// (ADR-0008). Turns that only change parameters, prices or variants, undo, or ask about the
// project are routine tool calls for a fast, cheaper model. When in doubt the designer is used:
// a wrong "fast" decision costs quality, a wrong "designer" decision only costs money.

// Model roles.
const (
	RoleDesigner = "designer"
	RoleFast     = "fast"
)

// RoutingVersion is part of the prompt fingerprint; raise it when the rules change.
const RoutingVersion = "2"

// Unicode-aware stand-ins for Python's `\b` (Go's `\b` only knows ASCII word characters). They
// consume the neighbouring character, which is fine for matching.
const (
	wb  = `(?:^|[^\p{L}\p{N}_])`
	wbe = `(?:$|[^\p{L}\p{N}_])`
)

var (
	// Words that ask for a new or changed construction (beyond parameters).
	structuralPattern = regexp.MustCompile(`(?i)entw(?:u|ü|ue)rf|konstru|umbau|bau(?:e|t)?\s+(?:mir|eine?n?)` + wbe + `.*` + wb + `(?:mit|ohne)` + wbe + `|` +
		`zus(?:ä|ae)tzlich|schublade|klappe|t(?:ü|ue)r(?:en)?` + wbe + `|fach` + wbe + `|f(?:ä|ae)cher|` +
		`(?:statt|anstatt|anders|andere\s+bauweise)`)
	undoPattern = regexp.MustCompile(`(?i)r(?:ü|ue)ckg(?:ä|ae)ngig|undo`)
	// Python applied `\b` after "€" too, so "5€" only matched when a word character followed.
	pricePattern     = regexp.MustCompile(`(?i)\d+(?:[.,]\d+)?\s*(?:€[\p{L}\p{N}_]|(?:eur|euro)` + wbe + `)|kostet\s+bei\s+mir`)
	parameterPattern = regexp.MustCompile(`(?i)` + wb + `(?:breite|l(?:ä|ae)nge|h(?:ö|oe)he|tiefe|st(?:ä|ae)rke|holzart|lasur|(?:ö|oe)l|` +
		`unbehandelt|l(?:ä|ae)rche|douglasie|fichte|kiefer|eiche)` + wbe + `.*\d|` +
		wb + `(?:in|aus)\s+(?:l(?:ä|ae)rche|douglasie|fichte|kiefer|eiche)` + wbe)
	questionPattern = regexp.MustCompile(`(?i)^\s*(?:warum|wieso|weshalb|was|wie\s+viel|wieviel|welche|kann\s+ich|muss\s+ich)` + wbe)
)

// Route is the model role for a turn and why it was chosen.
type Route struct {
	Role   string
	Reason string
}

// RouteMessage picks the role for a user message; hasProject = an active project is edited.
func RouteMessage(text string, hasProject bool) Route {
	lowered := strings.ToLower(text)
	if structuralPattern.MatchString(lowered) {
		return Route{RoleDesigner, "structural"}
	}
	if hasProject {
		switch {
		case undoPattern.MatchString(lowered):
			return Route{RoleFast, "undo"}
		case deltaPattern.MatchString(lowered):
			return Route{RoleFast, "relative_change"}
		case pricePattern.MatchString(lowered):
			return Route{RoleFast, "price"}
		case mentionsVariant(lowered):
			return Route{RoleFast, "variant"}
		case parameterPattern.MatchString(lowered):
			return Route{RoleFast, "parameters"}
		case questionPattern.MatchString(lowered):
			return Route{RoleFast, "question"}
		}
	}
	return Route{RoleDesigner, "default"}
}

func mentionsVariant(lowered string) bool {
	if !strings.Contains(lowered, "variante") {
		return false
	}
	for _, v := range variantWords {
		if strings.Contains(lowered, v.word) {
			return true
		}
	}
	return false
}
