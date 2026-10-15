// Package compliance holds the safety gate, fixed notice texts (AI Act Art. 50, liability,
// building law) and the redaction of personal data before text reaches an LLM.
package compliance

import (
	"regexp"
	"strings"
)

// SafetyRulesVersion is stored with every agent run; raise it when the rules change.
const SafetyRulesVersion = "2"

// Unicode-aware replacements for Python's `\b` (Go's `\b` only knows ASCII word characters).
const (
	wordStart = `(?:^|[^\p{L}\p{N}_])`
	wordEnd   = `(?:$|[^\p{L}\p{N}_])`
)

// SafetyTopic is a subject that must be handled by licensed professionals.
type SafetyTopic struct {
	Key      string
	pattern  *regexp.Regexp
	Response string
}

func pattern(alternatives ...string) *regexp.Regexp {
	return regexp.MustCompile(`(?i)` + strings.Join(alternatives, "|"))
}

// Topics are checked in order; the first match wins. Rules are deliberately conservative: a false
// positive only costs a referral.
var Topics = []SafetyTopic{
	{
		Key: "electrical",
		pattern: pattern(
			`steckdose`,
			`sicherungskasten`,
			`unterverteilung`,
			`stromkreis`,
			`elektroinstallation`,
			`starkstrom`,
			wordStart+`(230|400)\s?v(olt)?`+wordEnd,
			wordStart+`fi[- ]?schalter`,
			`lichtschalter`,
			`(strom|elektro)leitung`,
			`kabel\s+(verlegen|anschlie)`,
		),
		Response: "Arbeiten an der festen Elektroinstallation (230/400 V) dürfen nur Elektrofachkräfte " +
			"bzw. im Installateurverzeichnis eingetragene Betriebe ausführen. Dafür erstelle ich " +
			"keine Bauanleitung. Ich kann dir aber helfen, das übrige Vorhaben zu planen und " +
			"z. B. eine Leerrohr-Trasse für den Elektriker vorzusehen.",
	},
	{
		Key: "gas_fire",
		pattern: pattern(
			wordStart+`gas(leitung|therme|herd|anschluss|flasche[\p{L}\p{N}_]* anschlie)`,
			`kamin`,
			`schornstein`,
			`feuerst(ä|ae)tte`,
			`ofen\s*(einbauen|anschlie|setzen)`,
			`abgasrohr`,
		),
		Response: "Gasanlagen, Feuerstätten und Abgasanlagen gehören in die Hand eines Fachbetriebs; " +
			"Feuerstätten nimmt zudem der Bezirksschornsteinfeger ab. Dafür gebe ich keine " +
			"Bauanleitung. Bei Planung, Materialauswahl für das Umfeld oder Fragen an den " +
			"Fachbetrieb helfe ich gern.",
	},
	{
		Key: "structural",
		pattern: pattern(
			`tragende[\p{L}\p{N}_]*\s+wand`,
			`wanddurchbruch`,
			`deckendurchbruch`,
			`decke\s+(öffnen|durchbrechen|entfernen)`,
			// Changes to an existing roof structure; planning a new house is allowed (ADR-0007).
			`dachstuhl[\p{L}\p{N}_]*\s+(ändern|aendern|umbauen|kürzen|kuerzen|absägen|entfernen|öffnen)`,
			`(sparren|kehlbalken|pfette)[\p{L}\p{N}_]*\s+(kürzen|kuerzen|durchsägen|absägen|entfernen)`,
			`st(ü|ue)tze\s+entfernen`,
			`tr(ä|ae)ger\s+(einziehen|entfernen)`,
		),
		Response: "Eingriffe in tragende Bauteile (Wände, Decken, Dachstuhl) betreffen die " +
			"Standsicherheit des Gebäudes und brauchen einen Tragwerksplaner – oft auch eine " +
			"Genehmigung. Dafür erstelle ich keine Anleitung, kann dir aber helfen, die Fragen " +
			"an den Planer vorzubereiten.",
	},
	{
		Key: "hazardous",
		pattern: pattern(
			`asbest`,
			`eternit`,
			`nachtspeicher`,
			wordStart+`pcp`+wordEnd,
			`lindan`,
			`teer(pappe|kleber)`,
		),
		Response: "Bei Verdacht auf Asbest oder alte Holzschutzmittel (z. B. PCP, Lindan) – typisch " +
			"für Bauten und Materialien vor 1993 – bitte nichts selbst entfernen, schleifen oder " +
			"bohren. Das dürfen nur Fachbetriebe mit Sachkunde nach TRGS 519. Lass das Material " +
			"vorher prüfen.",
	},
}

// SafetyVerdict is the outcome of the safety gate for one message.
type SafetyVerdict struct {
	Blocked  bool
	Topic    string
	Response string
}

// CheckMessage runs the safety gate on a user message.
func CheckMessage(text string) SafetyVerdict {
	for _, topic := range Topics {
		if topic.pattern.MatchString(text) {
			return SafetyVerdict{Blocked: true, Topic: topic.Key, Response: topic.Response}
		}
	}
	return SafetyVerdict{}
}
