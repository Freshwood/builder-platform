// Package model is the pure domain model of Homeworking, ported from the Python package
// construction_model: project inputs, the parametric AssemblyDesign, the engine result, the
// drawing IR, commands with undo and the result diff.
//
// JSON decoding and encoding follow pydantic (see codec.go): field names are snake_case,
// missing fields get their defaults, unknown fields are rejected where the Python model has
// extra="forbid", and the output matches model_dump(mode="json"). The package does no I/O.
package model

// Mm is a length in millimetres.
type Mm = int

// Origin tells who produced a piece of content (relevant for AI Act Art. 50 labelling).
type Origin string

// Origins.
const (
	OriginUser   Origin = "user"
	OriginEngine Origin = "engine"
	OriginAI     Origin = "ai"
)

func (Origin) pyChoices() ([]string, bool) { return []string{"user", "engine", "ai"}, true }
