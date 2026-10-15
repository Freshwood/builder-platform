package model

// Renderer-independent drawing intermediate representation (IR). Coordinates are millimetres
// in model space, x to the right, y downwards. Renderers (SVG now, DXF/PDF later) consume this
// IR, so all outputs stay dimensionally consistent.

// Stroke is a line style.
type Stroke string

// Strokes.
const (
	StrokeOutline  Stroke = "outline"
	StrokeThin     Stroke = "thin"
	StrokeHidden   Stroke = "hidden"
	StrokeCenter   Stroke = "center"
	StrokeMembrane Stroke = "membrane"
)

func (Stroke) pyChoices() ([]string, bool) {
	return []string{"outline", "thin", "hidden", "center", "membrane"}, true
}

// Fill is a hatch or fill style.
type Fill string

// Fills.
const (
	FillNone     Fill = "none"
	FillWood     Fill = "wood"
	FillWoodEnd  Fill = "wood_end"
	FillSteel    Fill = "steel"
	FillMembrane Fill = "membrane"
	FillGround   Fill = "ground"
)

func (Fill) pyChoices() ([]string, bool) {
	return []string{"none", "wood", "wood_end", "steel", "membrane", "ground"}, true
}

// Primitive is one drawing element: Rect, Line, Dimension, Label, Polygon or Callout. In JSON
// it is a union discriminated by "kind".
type Primitive interface {
	unionMember
	isPrimitive()
}

// Rect is a rectangle (kind "rect"). Use New[Rect]() for the defaults (outline, no fill).
type Rect struct {
	X      float64 `json:"x"`
	Y      float64 `json:"y"`
	W      float64 `json:"w"`
	H      float64 `json:"h"`
	Stroke Stroke  `json:"stroke" def:"\"outline\""`
	Fill   Fill    `json:"fill" def:"\"none\""`
	Label  *string `json:"label" def:"null"`
}

// Line is a straight line (kind "line"). Use New[Line]() for the default thin stroke.
type Line struct {
	X1     float64 `json:"x1"`
	Y1     float64 `json:"y1"`
	X2     float64 `json:"x2"`
	Y2     float64 `json:"y2"`
	Stroke Stroke  `json:"stroke" def:"\"thin\""`
}

// Dimension is a linear dimension between two points, drawn Offset mm away from the measured
// line (kind "dimension").
type Dimension struct {
	X1     float64 `json:"x1"`
	Y1     float64 `json:"y1"`
	X2     float64 `json:"x2"`
	Y2     float64 `json:"y2"`
	Offset float64 `json:"offset"`
	Text   string  `json:"text"`
}

// LabelAnchor is the text anchor of a label.
type LabelAnchor string

func (LabelAnchor) pyChoices() ([]string, bool) { return []string{"start", "middle", "end"}, false }

// LabelSize is the text size of a label.
type LabelSize string

func (LabelSize) pyChoices() ([]string, bool) { return []string{"small", "normal"}, false }

// Label is a text (kind "label"). Use New[Label]() for the defaults (start, normal).
type Label struct {
	X      float64     `json:"x"`
	Y      float64     `json:"y"`
	Text   string      `json:"text"`
	Anchor LabelAnchor `json:"anchor" def:"\"start\""`
	Size   LabelSize   `json:"size" def:"\"normal\""`
}

// Polygon is a filled face of a projected solid (kind "polygon"). Tone names a material colour,
// Shade (0..1) its light. Use New[Polygon]() for the default shade 1.
type Polygon struct {
	Points [][2]float64   `json:"points"`
	Tone   string         `json:"tone"`
	Shade  float64        `json:"shade" def:"1.0" v:"ge=0,le=1"`
	Holes  [][][2]float64 `json:"holes" def:"[]"`
}

// Callout is a position bubble at (BX, BY) with a leader line to the target point (X, Y)
// (kind "callout").
type Callout struct {
	X    float64 `json:"x"`
	Y    float64 `json:"y"`
	BX   float64 `json:"bx"`
	BY   float64 `json:"by"`
	Text string  `json:"text"`
}

func (Rect) unionTag() (string, string)      { return "kind", "rect" }
func (Line) unionTag() (string, string)      { return "kind", "line" }
func (Dimension) unionTag() (string, string) { return "kind", "dimension" }
func (Label) unionTag() (string, string)     { return "kind", "label" }
func (Polygon) unionTag() (string, string)   { return "kind", "polygon" }
func (Callout) unionTag() (string, string)   { return "kind", "callout" }

func (Rect) isPrimitive()      {}
func (Line) isPrimitive()      {}
func (Dimension) isPrimitive() {}
func (Label) isPrimitive()     {}
func (Polygon) isPrimitive()   {}
func (Callout) isPrimitive()   {}

// PrimitiveKind returns the discriminator of a primitive ("rect", "line", ...).
func PrimitiveKind(p Primitive) string {
	_, tag := p.unionTag()
	return tag
}

func init() {
	registerUnion[Primitive]("kind", Rect{}, Line{}, Dimension{}, Label{}, Polygon{}, Callout{})
}

// LegendEntry maps a material tone to its label.
type LegendEntry struct {
	Tone  string `json:"tone"`
	Label string `json:"label"`
}

// Drawing is one view with its primitives. Primitives are omitted in API project views
// (clients load the rendered SVG instead).
type Drawing struct {
	View        string        `json:"view"`
	Title       string        `json:"title"`
	Description string        `json:"description"`
	ScaleHint   string        `json:"scale_hint"`
	MinX        float64       `json:"min_x"`
	MinY        float64       `json:"min_y"`
	Width       float64       `json:"width"`
	Height      float64       `json:"height"`
	Primitives  []Primitive   `json:"primitives" def:"[]"`
	Legend      []LegendEntry `json:"legend" def:"[]"`
}
