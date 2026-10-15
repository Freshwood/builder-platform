package compliance

import "regexp"

type redactionRule struct {
	pattern     *regexp.Regexp
	replacement string
}

// Each pattern that needs a word boundary or a negative lookbehind before the match captures the
// preceding character in group 1 and puts it back in the replacement.
var redactionRules = []redactionRule{
	{regexp.MustCompile(`[\p{L}\p{N}_.+-]+@[\p{L}\p{N}_-]+\.[\p{L}\p{N}_.-]+`), "[E-MAIL]"},
	{regexp.MustCompile(`(^|[^\p{L}\p{N}_])[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,4})?\b`), "${1}[IBAN]"},
	{regexp.MustCompile(`(^|[^\p{L}\p{N}_])(?:\+49|0049|0)[\s/-]?\d{2,5}[\s/-]?\d{3,}(?:[\s-]?\d+)*`), "${1}[TELEFON]"},
	{
		regexp.MustCompile(`(^|[^\p{L}\p{N}_])[A-ZÄÖÜ][\p{L}\p{N}_äöüß-]*(?:straße|strasse|str\.|weg|allee|platz|gasse|ring|damm)` +
			`\s+\d+\s?[a-zA-Z]?\b`),
		"${1}[ADRESSE]",
	},
	{regexp.MustCompile(`(?i)(^|[^\p{L}\p{N}_])(?:Flurst(?:ück|ueck)|Flur)\s*(?:Nr\.?\s*)?[\d/]+`), "${1}[FLURSTÜCK]"},
}

// Redact removes personal data (e-mail, IBAN, phone, street address, land parcel) heuristically
// from text before it is sent to an LLM (GDPR Art. 5/25).
func Redact(text string) string {
	for _, rule := range redactionRules {
		text = rule.pattern.ReplaceAllString(text, rule.replacement)
	}
	return text
}
