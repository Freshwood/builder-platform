package model

import (
	"fmt"
	"math"

	"github.com/shopspring/decimal"
)

// Typed commands are the only way to change a project's inputs. They are produced by the UI or
// proposed by the agent, validated, applied to the inputs and appended to the project's command
// log. Undo is itself a logged command; the effective command sequence is obtained with stack
// semantics (EffectiveCommands).

// CommandError is returned when a command cannot be applied to the current inputs.
type CommandError struct {
	Msg string
}

func (e *CommandError) Error() string { return e.Msg }

func commandErr(format string, args ...any) error {
	return &CommandError{Msg: fmt.Sprintf(format, args...)}
}

// Command is any command that can be stored in the command log. In JSON it is a union
// discriminated by "type".
type Command interface {
	unionMember
	isCommand()
}

// EditCommand is a command that clients may submit for an existing project.
type EditCommand interface {
	Command
	isEditCommand()
}

// CreateProject creates the project (always the first command).
type CreateProject struct {
	Title  string           `json:"title" v:"minlen=1,maxlen=200"`
	Design AssemblyDesign   `json:"design"`
	Params Dict[ParamValue] `json:"params" def:"{}"`
	Region *Region          `json:"region" def:"null"`
}

// SetParameters sets one or more parameters to absolute values (lengths in mm).
type SetParameters struct {
	Values Dict[ParamValue] `json:"values" v:"minitems=1"`
}

// ChangeParameterBy changes a numeric parameter relatively, e.g. width_mm by +500.
type ChangeParameterBy struct {
	Name  string `json:"name"`
	Delta int    `json:"delta"`
}

// SelectVariant applies a design variant's overrides.
type SelectVariant struct {
	VariantKey string `json:"variant_key"`
}

// Rename sets the project title.
type Rename struct {
	Title string `json:"title" v:"minlen=1,maxlen=200"`
}

// SetRegion sets or clears (nil) the federal state.
type SetRegion struct {
	Region *Region `json:"region"`
}

// AddNote attaches a note. Id and timestamp live in the command so that replay is
// deterministic. Use New[AddNote]() to get a fresh id, the current time and origin "user".
type AddNote struct {
	Text      string   `json:"text" v:"minlen=1,maxlen=4000"`
	Origin    Origin   `json:"origin" def:"\"user\""`
	NoteID    UUID     `json:"note_id" def:"uuid4"`
	CreatedAt DateTime `json:"created_at" def:"now"`
}

// ReplaceDesign replaces the free-form design; keeps valid params and user notes, drops AI
// explanations.
type ReplaceDesign struct {
	Design AssemblyDesign `json:"design"`
}

// SetPrice sets the user's own unit price for a BOM item (EUR); nil returns to the guide price.
type SetPrice struct {
	ItemID    string           `json:"item_id" v:"minlen=1,maxlen=120"`
	UnitPrice *decimal.Decimal `json:"unit_price" def:"null" v:"ge=0,le=100000,places=2"`
}

// ReplaceInputs replaces all inputs at once: restore an earlier version or re-plan the project.
// The full inputs travel with the command, so replaying the log never depends on other entries.
type ReplaceInputs struct {
	Inputs ProjectInputs `json:"inputs"`
	// RestoredSeq is the version restored by this command.
	RestoredSeq *int `json:"restored_seq" def:"null" v:"ge=1"`
}

// Undo reverts the latest effective command.
type Undo struct{}

func (CreateProject) unionTag() (string, string)     { return "type", "create_project" }
func (SetParameters) unionTag() (string, string)     { return "type", "set_parameters" }
func (ChangeParameterBy) unionTag() (string, string) { return "type", "change_parameter_by" }
func (SelectVariant) unionTag() (string, string)     { return "type", "select_variant" }
func (Rename) unionTag() (string, string)            { return "type", "rename" }
func (SetRegion) unionTag() (string, string)         { return "type", "set_region" }
func (AddNote) unionTag() (string, string)           { return "type", "add_note" }
func (ReplaceDesign) unionTag() (string, string)     { return "type", "replace_design" }
func (SetPrice) unionTag() (string, string)          { return "type", "set_price" }
func (ReplaceInputs) unionTag() (string, string)     { return "type", "replace_inputs" }
func (Undo) unionTag() (string, string)              { return "type", "undo" }

func (CreateProject) isCommand()     {}
func (SetParameters) isCommand()     {}
func (ChangeParameterBy) isCommand() {}
func (SelectVariant) isCommand()     {}
func (Rename) isCommand()            {}
func (SetRegion) isCommand()         {}
func (AddNote) isCommand()           {}
func (ReplaceDesign) isCommand()     {}
func (SetPrice) isCommand()          {}
func (ReplaceInputs) isCommand()     {}
func (Undo) isCommand()              {}

func (SetParameters) isEditCommand()     {}
func (ChangeParameterBy) isEditCommand() {}
func (SelectVariant) isEditCommand()     {}
func (Rename) isEditCommand()            {}
func (SetRegion) isEditCommand()         {}
func (AddNote) isEditCommand()           {}
func (ReplaceDesign) isEditCommand()     {}
func (SetPrice) isEditCommand()          {}

// CommandType returns the discriminator of a command ("create_project", ...).
func CommandType(c Command) string {
	_, tag := c.unionTag()
	return tag
}

func init() {
	registerUnion[Command]("type",
		CreateProject{}, SetParameters{}, ChangeParameterBy{}, SelectVariant{}, Rename{},
		SetRegion{}, AddNote{}, ReplaceDesign{}, SetPrice{}, ReplaceInputs{}, Undo{})
	registerUnion[EditCommand]("type",
		SetParameters{}, ChangeParameterBy{}, SelectVariant{}, Rename{}, SetRegion{},
		AddNote{}, ReplaceDesign{}, SetPrice{})
}

// UnmarshalCommand decodes and validates any command (the Python command_adapter).
func UnmarshalCommand(data []byte) (Command, error) {
	var c Command
	if err := Decode(data, &c); err != nil {
		return nil, err
	}
	return c, nil
}

// UnmarshalEditCommand decodes and validates a command a client may submit for an existing
// project.
func UnmarshalEditCommand(data []byte) (EditCommand, error) {
	var c EditCommand
	if err := Decode(data, &c); err != nil {
		return nil, err
	}
	return c, nil
}

// MarshalCommand encodes a command with its "type" tag.
func MarshalCommand(c Command) ([]byte, error) { return Encode(c) }

// stillValid reports whether a parameter value can be carried over to a replaced design.
func stillValid(design AssemblyDesign, name string, value ParamValue) bool {
	spec, ok := design.Param(name)
	if !ok {
		return false
	}
	switch spec.Kind {
	case ParamBool:
		return value.Kind() == BoolKind
	case ParamChoice:
		s, isStr := value.Str()
		if !isStr {
			return false
		}
		for _, o := range spec.Options {
			if o.Value == s {
				return true
			}
		}
		return false
	default:
		if !value.IsNumber() {
			return false
		}
		low, high := math.Inf(-1), math.Inf(1)
		if spec.Min != nil {
			low = *spec.Min
		}
		if spec.Max != nil {
			high = *spec.Max
		}
		f, _ := value.Float()
		if i, isInt := value.Int(); isInt {
			return cmpIntFloat(i, low) >= 0 && cmpIntFloat(i, high) <= 0
		}
		return low <= f && f <= high
	}
}

// cmpIntFloat compares an int with a float exactly, as Python does.
func cmpIntFloat(i int64, f float64) int {
	switch {
	case math.IsInf(f, 1) || math.IsNaN(f):
		return -1
	case math.IsInf(f, -1):
		return 1
	}
	fi := float64(i)
	if fi < f {
		return -1
	}
	if fi > f {
		return 1
	}
	// Equal as floats: decide with the exact integer part of f.
	if f >= 9.223372036854775807e18 {
		return -1
	}
	t := int64(f)
	switch {
	case i < t:
		return -1
	case i > t:
		return 1
	}
	return 0
}

// ApplyToInputs applies a single (non-undo) command and returns new inputs. inputs is nil for
// a project that does not exist yet. variantOverrides maps variant keys to their overrides.
//
// Parameter values are not range-checked here; that is the job of the engine, which checks
// them against the design's parameter declarations.
func ApplyToInputs(inputs *ProjectInputs, command Command, variantOverrides map[string]Dict[ParamValue]) (ProjectInputs, error) {
	if c, ok := command.(CreateProject); ok {
		if inputs != nil {
			return ProjectInputs{}, commandErr("Project already exists")
		}
		return ProjectInputs{
			Title:  c.Title,
			Design: c.Design,
			Params: c.Params.Clone(),
			Region: c.Region,
		}, nil
	}
	if inputs == nil {
		return ProjectInputs{}, commandErr("The first command must create the project")
	}
	out := inputs.Clone()
	switch c := command.(type) {
	case SetParameters:
		out.Params = out.Params.Merge(c.Values)
	case ChangeParameterBy:
		current, ok := inputs.Params.Get(c.Name)
		if !ok {
			if spec, found := inputs.Design.Param(c.Name); found {
				current, ok = spec.Default, true
			}
		}
		if !ok || !current.IsNumber() {
			return ProjectInputs{}, commandErr("Parameter '%s' is not numeric or not set", c.Name)
		}
		if i, isInt := current.Int(); isInt {
			out.Params.Set(c.Name, IntValue(i+int64(c.Delta)))
		} else {
			f, _ := current.Float()
			out.Params.Set(c.Name, FloatValue(f+float64(c.Delta)))
		}
	case SelectVariant:
		overrides, ok := variantOverrides[c.VariantKey]
		if !ok {
			return ProjectInputs{}, commandErr("Unknown variant '%s'", c.VariantKey)
		}
		out.Params = out.Params.Merge(overrides)
		key := c.VariantKey
		out.VariantKey = &key
	case Rename:
		out.Title = c.Title
	case SetRegion:
		out.Region = c.Region
	case AddNote:
		out.Notes = append(out.Notes, Note{ID: c.NoteID, Origin: c.Origin, Text: c.Text, CreatedAt: c.CreatedAt})
	case ReplaceDesign:
		kept := Dict[ParamValue]{}
		for k, v := range inputs.Params.All() {
			if stillValid(c.Design, k, v) {
				kept.Set(k, v)
			}
		}
		// AI explanations describe the replaced construction; user notes stay.
		notes := []Note{}
		for _, n := range inputs.Notes {
			if n.Origin != OriginAI {
				notes = append(notes, n)
			}
		}
		out.Design = c.Design
		out.Params = kept
		out.VariantKey = nil
		out.Notes = notes
	case SetPrice:
		out.Prices.Delete(c.ItemID)
		if c.UnitPrice != nil {
			out.Prices.Set(c.ItemID, *c.UnitPrice)
		}
	case ReplaceInputs:
		return c.Inputs, nil
	case Undo:
		return ProjectInputs{}, commandErr("Undo must be resolved via EffectiveCommands()")
	default:
		return ProjectInputs{}, commandErr("Unsupported command %T", command)
	}
	return out, nil
}

// LogEntry is one command of a command log with a caller-defined key (e.g. its sequence number).
type LogEntry[T any] struct {
	Key     T
	Command Command
}

// EffectiveCommands resolves undo entries with stack semantics. The create command can never
// be undone.
func EffectiveCommands[T any](log []LogEntry[T]) ([]LogEntry[T], error) {
	var stack []LogEntry[T]
	for _, entry := range log {
		if _, isUndo := entry.Command.(Undo); isUndo {
			if len(stack) <= 1 {
				return nil, commandErr("Nothing to undo")
			}
			stack = stack[:len(stack)-1]
			continue
		}
		stack = append(stack, entry)
	}
	return stack, nil
}

// CanUndo reports whether an undo would succeed on the log.
func CanUndo(log []Command) bool {
	entries := make([]LogEntry[struct{}], len(log))
	for i, c := range log {
		entries[i] = LogEntry[struct{}]{Command: c}
	}
	eff, err := EffectiveCommands(entries)
	return err == nil && len(eff) > 1
}
