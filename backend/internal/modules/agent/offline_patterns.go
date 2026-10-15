package agent

import "regexp"

// numPattern is a number with decimal point or comma.
const numPattern = `(\d+(?:[.,]\d+)?)`

// deltaPattern matches "50 cm breiter" and friends (offline planner and routing).
var deltaPattern = regexp.MustCompile(`(?i)` + numPattern + `\s*(mm|cm|m)\b\s*(breiter|schmaler|l(?:ä|ae)nger|k(?:ü|ue)rzer|h(?:ö|oe)her|niedriger)`)

// variantWords map words to variant keys (order as in the former Python dict).
var variantWords = []struct{ word, key string }{
	{"günstig", "budget"},
	{"guenstig", "budget"},
	{"langlebig", "durable"},
	{"komfort", "comfort"},
}
