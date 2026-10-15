package model

import (
	"fmt"
	"sort"
	"strings"
)

// Parametric assembly design: the generic input format for free-form projects (ADR-0004).
//
// A design describes what is built: named parameters and parts (boxes, or members between two
// points) whose size and position are expressions over those parameters, optionally with an
// outline shape, cutouts, end cuts and carpentry joints. Everything derived from it is computed
// by the engine.
//
// Coordinates (millimetres): x to the right (width), y to the back (depth), z up (height). The
// floor is z = 0. A part's At is its minimum corner (front-left-bottom) before rotation.

// Vec3 is a point or extent of three expressions.
type Vec3 = [3]Expr

// Vec2 is a point of two expressions in a face's (u, v) coordinates.
type Vec2 = [2]Expr

// Use is where the object stands: "indoor" or "outdoor".
type Use string

// Uses.
const (
	UseIndoor  Use = "indoor"
	UseOutdoor Use = "outdoor"
)

func (Use) pyChoices() ([]string, bool) { return []string{"indoor", "outdoor"}, false }

// Support is how the object is held: "floor" (stands on z=0) or "wall" (back side fixed).
type Support string

// Supports.
const (
	SupportFloor Support = "floor"
	SupportWall  Support = "wall"
)

func (Support) pyChoices() ([]string, bool) { return []string{"floor", "wall"}, false }

// Uses lists all Use values; Supports all Support values.
var (
	Uses     = []Use{UseIndoor, UseOutdoor}
	Supports = []Support{SupportFloor, SupportWall}
)

// Category is "object" or "building".
type Category string

// Categories.
const (
	CategoryObject   Category = "object"
	CategoryBuilding Category = "building"
)

func (Category) pyChoices() ([]string, bool) { return []string{"object", "building"}, false }

// ChoiceOption is one option of a choice parameter.
type ChoiceOption struct {
	Value string `json:"value" v:"pattern=choice"`
	Label string `json:"label" v:"minlen=1,maxlen=60"`
}

// DesignParamKind is the kind of a design parameter.
type DesignParamKind string

// Design parameter kinds.
const (
	ParamLength DesignParamKind = "length"
	ParamCount  DesignParamKind = "count"
	ParamAngle  DesignParamKind = "angle"
	ParamBool   DesignParamKind = "bool"
	ParamChoice DesignParamKind = "choice"
)

func (DesignParamKind) pyChoices() ([]string, bool) {
	return []string{"length", "count", "angle", "bool", "choice"}, false
}

// exampleRange holds example bounds quoted in the error for a numeric parameter without min/max.
var exampleRange = map[DesignParamKind][2]int{
	ParamLength: {300, 1200},
	ParamCount:  {1, 10},
	ParamAngle:  {0, 90},
}

func knownIDs(known []string) string {
	shown := known
	if len(shown) > 15 {
		shown = shown[:15]
	}
	out := strings.Join(shown, ", ")
	if len(known) > 15 {
		out += " …"
	}
	return out
}

// DesignParam is a user-adjustable parameter. Lengths are millimetres and should end in "_mm".
type DesignParam struct {
	Name    string          `json:"name" v:"pattern=ident"`
	Label   string          `json:"label" v:"minlen=1,maxlen=80"`
	Kind    DesignParamKind `json:"kind"`
	Default ParamValue      `json:"default"`
	Min     *float64        `json:"min" def:"null"`
	Max     *float64        `json:"max" def:"null"`
	Options []ChoiceOption  `json:"options" def:"[]"`
}

func (p DesignParam) validateModel() error {
	switch p.Kind {
	case ParamLength, ParamCount, ParamAngle:
		if p.Min == nil || p.Max == nil {
			r := exampleRange[p.Kind]
			return fmt.Errorf("Parameter '%s' (Art %s) braucht min und max, "+
				`z. B. "min": %d, "max": %d und einen default dazwischen`, p.Name, p.Kind, r[0], r[1])
		}
		if *p.Min > *p.Max {
			return fmt.Errorf("Parameter '%s': min (%s) ist größer als max (%s) – Werte vertauscht?",
				p.Name, FormatG(*p.Min), FormatG(*p.Max))
		}
	}
	if p.Kind == ParamChoice && len(p.Options) == 0 {
		return fmt.Errorf("Auswahl-Parameter '%s' braucht options, "+
			`z. B. [{"value": "oak", "label": "Eiche"}] und einen default aus den values`, p.Name)
	}
	return nil
}

// Axis is "x", "y" or "z".
type Axis string

// Axes.
const (
	AxisX Axis = "x"
	AxisY Axis = "y"
	AxisZ Axis = "z"
)

func (Axis) pyChoices() ([]string, bool) { return []string{"x", "y", "z"}, false }

// Rotation is a rotation about an axis through the part's At point (right-hand rule).
type Rotation struct {
	Axis Axis `json:"axis"`
	Deg  Expr `json:"deg"`
}

// Repeat repeats a part Count times; Var (0-based index) is usable in its expressions.
type Repeat struct {
	Count Expr   `json:"count"`
	Var   string `json:"var" def:"\"i\"" v:"pattern=ident"`
}

// ShapeKind is the outline kind of a part.
type ShapeKind string

// Shape kinds.
const (
	ShapeRect     ShapeKind = "rect"
	ShapeRounded  ShapeKind = "rounded"
	ShapeEllipse  ShapeKind = "ellipse"
	ShapeTriangle ShapeKind = "triangle"
	ShapeArch     ShapeKind = "arch"
	ShapeCloud    ShapeKind = "cloud"
	ShapePolygon  ShapeKind = "polygon"
)

func (ShapeKind) pyChoices() ([]string, bool) {
	return []string{"rect", "rounded", "ellipse", "triangle", "arch", "cloud", "polygon"}, false
}

// EndCut is the cut at one end of a member.
type EndCut string

// End cuts.
const (
	EndCutSquare EndCut = "square"
	EndCutLevel  EndCut = "level"
	EndCutPlumb  EndCut = "plumb"
	EndCutCorner EndCut = "corner"
)

func (EndCut) pyChoices() ([]string, bool) {
	return []string{"square", "level", "plumb", "corner"}, false
}

// Shape is an outline on the face across the thinnest size; (u, v) in mm from the minimum
// corner, u along the first remaining axis in x, y, z order (members: along the length).
type Shape struct {
	Kind   ShapeKind `json:"kind"`
	Radius *Expr     `json:"radius" def:"null"`
	Apex   *Expr     `json:"apex" def:"null"`
	Bumps  *int      `json:"bumps" def:"null" v:"ge=2,le=12"`
	Points []Vec2    `json:"points" def:"[]" v:"maxitems=40"`
}

// CutoutKind is the kind of a cutout.
type CutoutKind string

// Cutout kinds.
const (
	CutoutRect    CutoutKind = "rect"
	CutoutEllipse CutoutKind = "ellipse"
	CutoutPolygon CutoutKind = "polygon"
)

func (CutoutKind) pyChoices() ([]string, bool) {
	return []string{"rect", "ellipse", "polygon"}, false
}

// Cutout is a hole in (u, v): rect/ellipse by At and Size, polygon by Points.
type Cutout struct {
	Kind   CutoutKind `json:"kind" def:"\"rect\""`
	At     Vec2       `json:"at" def:"[0, 0]"`
	Size   Vec2       `json:"size" def:"[0, 0]"`
	Points []Vec2     `json:"points" def:"[]" v:"maxitems=40"`
}

// PartSpec is one part of a design: a box (Size + At) or a member (Start + End).
type PartSpec struct {
	ID       string    `json:"id" v:"pattern=ident"`
	Name     string    `json:"name" v:"minlen=1,maxlen=60"`
	Material string    `json:"material" v:"maxlen=80"`
	Size     *Vec3     `json:"size" def:"null"`
	At       *Vec3     `json:"at" def:"null"`
	Rotate   *Rotation `json:"rotate" def:"null"`
	Start    *Vec3     `json:"start" def:"null"`
	End      *Vec3     `json:"end" def:"null"`
	Section  *Vec2     `json:"section" def:"null"`
	Facing   *Axis     `json:"facing" def:"null"`
	Cuts     [2]EndCut `json:"cuts" def:"[\"square\", \"square\"]"`
	Shape    *Shape    `json:"shape" def:"null"`
	Cutouts  []Cutout  `json:"cutouts" def:"[]" v:"maxitems=12"`
	Repeat   *Repeat   `json:"repeat" def:"null"`
	When     *Expr     `json:"when" def:"null"`
}

// IsMember reports whether the part is a member between Start and End.
func (p PartSpec) IsMember() bool { return p.Start != nil && p.End != nil }

func (p PartSpec) validateModel() error {
	box := p.Size != nil && p.At != nil
	member := p.Start != nil && p.End != nil
	if box == member {
		var given []string
		for _, f := range []struct {
			name string
			set  bool
		}{{"size", p.Size != nil}, {"at", p.At != nil}, {"start", p.Start != nil}, {"end", p.End != nil}} {
			if f.set {
				given = append(given, f.name)
			}
		}
		g := strings.Join(given, ", ")
		if g == "" {
			g = "nichts"
		}
		return fmt.Errorf("Bauteil '%s': entweder size und at (Box) oder start und end (Stab) "+
			"angeben, nicht beides und nicht nur eines davon (angegeben: %s)", p.ID, g)
	}
	if member && p.Rotate != nil {
		return fmt.Errorf("Bauteil '%s': rotate gilt nur für Boxen (size/at), nicht für Stäbe – "+
			"einen Stab über start und end neigen", p.ID)
	}
	return nil
}

// HardwareSpec is explicit hardware, e.g. hinges, castors or brackets. Screws are added
// automatically.
type HardwareSpec struct {
	Item     string  `json:"item" v:"maxlen=80"`
	Quantity Expr    `json:"quantity"`
	Note     *string `json:"note" def:"null" v:"maxlen=120"`
	When     *Expr   `json:"when" def:"null"`
}

// JointKind is a carpentry joint kind.
type JointKind string

// Joint kinds.
const (
	JointTenon   JointKind = "tenon"
	JointHalfLap JointKind = "half_lap"
	JointNotch   JointKind = "notch"
)

func (JointKind) pyChoices() ([]string, bool) { return []string{"tenon", "half_lap", "notch"}, false }

// JointSpec is a carpentry joint between all touching or overlapping instances of two parts.
type JointSpec struct {
	Kind JointKind `json:"kind"`
	Part string    `json:"part" v:"pattern=ident"`
	Into string    `json:"into" v:"pattern=ident"`
}

// DesignStep is one assembly step; Parts are the part ids newly mounted in it.
type DesignStep struct {
	Title string   `json:"title" v:"minlen=1,maxlen=80"`
	Text  string   `json:"text" v:"minlen=1,maxlen=800"`
	Parts []string `json:"parts" def:"[]" v:"pattern=ident"`
}

// DesignVariant is a named set of parameter overrides.
type DesignVariant struct {
	Key         string           `json:"key" v:"pattern=ident"`
	Name        string           `json:"name" v:"minlen=1,maxlen=40"`
	Description string           `json:"description" v:"maxlen=200"`
	Overrides   Dict[ParamValue] `json:"overrides"`
}

// AssemblyDesign is a complete parametric design of a buildable object.
//
// Numeric fields (size, at, start, end, section, points, count, quantity, when, deg) take a
// number or an arithmetic expression over parameters and the repeat variable.
type AssemblyDesign struct {
	ObjectType string          `json:"object_type" v:"minlen=1,maxlen=60"`
	Summary    string          `json:"summary" v:"maxlen=200"`
	Category   Category        `json:"category" def:"\"object\""`
	Use        Use             `json:"use" def:"\"indoor\""`
	Support    Support         `json:"support" def:"\"floor\""`
	Origin     Origin          `json:"origin" def:"\"ai\""`
	Params     []DesignParam   `json:"params" v:"maxitems=30"`
	Parts      []PartSpec      `json:"parts" v:"minitems=1,maxitems=120"`
	Joints     []JointSpec     `json:"joints" def:"[]" v:"maxitems=40"`
	Hardware   []HardwareSpec  `json:"hardware" def:"[]" v:"maxitems=30"`
	AutoScrews bool            `json:"auto_screws" def:"true"`
	Finish     *string         `json:"finish" def:"null"`
	Steps      []DesignStep    `json:"steps" def:"[]" v:"maxitems=20"`
	Variants   []DesignVariant `json:"variants" def:"[]" v:"maxitems=4"`
}

// Param returns the parameter declaration with the given name.
func (d AssemblyDesign) Param(name string) (DesignParam, bool) {
	for _, p := range d.Params {
		if p.Name == name {
			return p, true
		}
	}
	return DesignParam{}, false
}

// Variant returns the variant with the given key.
func (d AssemblyDesign) Variant(key string) (DesignVariant, bool) {
	for _, v := range d.Variants {
		if v.Key == key {
			return v, true
		}
	}
	return DesignVariant{}, false
}

func duplicates(ids []string) []string {
	count := map[string]int{}
	for _, id := range ids {
		count[id]++
	}
	var out []string
	for id, n := range count {
		if n > 1 {
			out = append(out, id)
		}
	}
	sort.Strings(out)
	return out
}

func (d AssemblyDesign) validateModel() error {
	paramNames := make([]string, len(d.Params))
	for i, p := range d.Params {
		paramNames[i] = p.Name
	}
	partIDs := make([]string, len(d.Parts))
	for i, p := range d.Parts {
		partIDs[i] = p.ID
	}
	variantKeys := make([]string, len(d.Variants))
	for i, v := range d.Variants {
		variantKeys[i] = v.Key
	}
	for _, group := range []struct {
		label string
		ids   []string
	}{{"Parameter-Namen", paramNames}, {"Bauteil-IDs", partIDs}, {"Varianten-Keys", variantKeys}} {
		if dup := duplicates(group.ids); len(dup) > 0 {
			hint := ""
			if strings.Contains(group.label, "Bauteil") {
				hint = " (mehrere gleiche Teile: repeat statt Kopien)"
			}
			return fmt.Errorf("Doppelte %s: %s – jede ID nur einmal vergeben%s", group.label, strings.Join(dup, ", "), hint)
		}
	}
	known := map[string]bool{}
	for _, id := range partIDs {
		known[id] = true
	}
	unknownSet := map[string]bool{}
	for _, j := range d.Joints {
		for _, id := range []string{j.Part, j.Into} {
			if !known[id] {
				unknownSet[id] = true
			}
		}
	}
	if len(unknownSet) > 0 {
		unknown := make([]string, 0, len(unknownSet))
		for id := range unknownSet {
			unknown = append(unknown, id)
		}
		sort.Strings(unknown)
		return fmt.Errorf("joints nennen unbekannte Bauteil-IDs: %s – vorhandene IDs: %s", strings.Join(unknown, ", "), knownIDs(partIDs))
	}
	return nil
}
