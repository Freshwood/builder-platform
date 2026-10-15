package model

import "github.com/shopspring/decimal"

// Core project model. Inputs (design, parameters, selected variant) are separated from the
// derived result produced by the deterministic engine. Only inputs are changed by commands; the
// result is always recomputed. Lengths are integer millimetres, money is decimal.

// SchemaVersion is the version of the stored project model.
const SchemaVersion = 2

// Severity of a notice.
type Severity string

// Severities.
const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

func (Severity) pyChoices() ([]string, bool) { return []string{"info", "warning", "critical"}, true }

// Region is a German federal state; building regulations differ per state.
type Region string

// Regions.
const (
	RegionBW Region = "BW"
	RegionBY Region = "BY"
	RegionBE Region = "BE"
	RegionBB Region = "BB"
	RegionHB Region = "HB"
	RegionHH Region = "HH"
	RegionHE Region = "HE"
	RegionMV Region = "MV"
	RegionNI Region = "NI"
	RegionNW Region = "NW"
	RegionRP Region = "RP"
	RegionSL Region = "SL"
	RegionSN Region = "SN"
	RegionST Region = "ST"
	RegionSH Region = "SH"
	RegionTH Region = "TH"
)

var regionValues = []string{"BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH"}

func (Region) pyChoices() ([]string, bool) { return regionValues, true }

// RuleRef is a versioned engineering rule of thumb used by the engine (provenance).
type RuleRef struct {
	ID            string  `json:"id"`
	Version       string  `json:"version"`
	Title         string  `json:"title"`
	NormReference *string `json:"norm_reference" def:"null"`
}

// Profile is a rectangular cross-section.
type Profile struct {
	ThicknessMM Mm `json:"thickness_mm"`
	WidthMM     Mm `json:"width_mm"`
}

// Component is a physical part of the construction. IfcType eases a later IFC export.
type Component struct {
	GUID       UUID     `json:"guid"`
	IfcType    string   `json:"ifc_type"`
	Role       string   `json:"role"`
	Name       string   `json:"name"`
	MaterialID string   `json:"material_id"`
	Profile    *Profile `json:"profile" def:"null"`
	LengthMM   *Mm      `json:"length_mm" def:"null"`
	Quantity   int      `json:"quantity" def:"1"`
}

// Currency is the literal "EUR". The zero value is written as "EUR" as well.
type Currency string

// EUR is the only currency.
const EUR Currency = "EUR"

func (Currency) pyChoices() ([]string, bool) { return []string{"EUR"}, false }

func (c Currency) appendJSON(_ *encoder, buf []byte) []byte {
	if c == "" {
		c = EUR
	}
	return appendString(buf, string(c))
}

// Money is a price range.
type Money struct {
	Min      decimal.Decimal `json:"min"`
	Max      decimal.Decimal `json:"max"`
	Currency Currency        `json:"currency" def:"\"EUR\""`
}

// NewMoney returns a EUR range without rounding (see catalog.Money for the rounded variant).
func NewMoney(minimum, maximum decimal.Decimal) Money {
	return Money{Min: minimum, Max: maximum, Currency: EUR}
}

// PriceSource is "estimate" (catalog guide price) or "user" (entered by the user).
type PriceSource string

// Price sources.
const (
	PriceEstimate PriceSource = "estimate"
	PriceUser     PriceSource = "user"
)

func (PriceSource) pyChoices() ([]string, bool) { return []string{"estimate", "user"}, false }

// BomLine is one line of the bill of materials.
type BomLine struct {
	Position  int             `json:"position"`
	ItemID    string          `json:"item_id"`
	Name      string          `json:"name"`
	Spec      string          `json:"spec"`
	Quantity  decimal.Decimal `json:"quantity"`
	Unit      string          `json:"unit"`
	UnitPrice Money           `json:"unit_price"`
	Total     Money           `json:"total"`
	Note      *string         `json:"note" def:"null"`
	// PriceSource: estimate = catalog guide price (range), user = price entered by the user.
	PriceSource PriceSource `json:"price_source" def:"\"estimate\""`
	// UsedShare is the share of the purchased quantity this project uses (e.g. 0.12 of a screw
	// pack); nil = all of it.
	UsedShare *decimal.Decimal `json:"used_share" def:"null"`
	// SearchQuery is the search text to look the product up at retailers.
	SearchQuery string `json:"search_query" def:"\"\""`
}

// CutLine is one line of the cut list.
type CutLine struct {
	Part         string `json:"part"`
	Material     string `json:"material"`
	CrossSection string `json:"cross_section"`
	LengthMM     Mm     `json:"length_mm"`
	Count        int    `json:"count"`
	// WidthMM is the second cut dimension for sheet parts.
	WidthMM *Mm `json:"width_mm" def:"null"`
	// Position is the position number in drawings.
	Position *int `json:"position" def:"null"`
	// Note describes contour, cutouts, end cuts or tenons.
	Note *string `json:"note" def:"null"`
}

// StockPlan tells how cut pieces are distributed over purchased stock lengths.
type StockPlan struct {
	ItemID        string  `json:"item_id"`
	StockLengthMM Mm      `json:"stock_length_mm"`
	StockCount    int     `json:"stock_count"`
	WasteMM       Mm      `json:"waste_mm"`
	Name          *string `json:"name" def:"null"`
	// Bars holds the cut piece lengths per purchased bar (linear stock).
	Bars           [][]Mm `json:"bars" def:"[]"`
	UtilizationPct *int   `json:"utilization_pct" def:"null"`
}

// Tool is a tool needed for the build.
type Tool struct {
	Name     string  `json:"name"`
	Required bool    `json:"required" def:"true"`
	Note     *string `json:"note" def:"null"`
}

// FillLayer is a layer of infill material.
type FillLayer struct {
	Name        string `json:"name"`
	ThicknessMM Mm     `json:"thickness_mm"`
	VolumeL     int    `json:"volume_l"`
	Purchase    bool   `json:"purchase"`
}

// CostSummary sums up the costs.
type CostSummary struct {
	Material      Money  `json:"material"`
	ToolsOptional Money  `json:"tools_optional"`
	Note          string `json:"note"`
	// MaterialUsed is the cost of what the project actually consumes (opened packs pro rata).
	MaterialUsed *Money `json:"material_used" def:"null"`
	// UserPriced is the number of BOM lines priced by the user.
	UserPriced int `json:"user_priced" def:"0"`
}

// InstructionStep is one step of the build instructions.
type InstructionStep struct {
	Number int    `json:"number"`
	Title  string `json:"title"`
	Text   string `json:"text"`
	Origin Origin `json:"origin" def:"\"engine\""`
	// Details are concrete sub-steps in working order.
	Details []string `json:"details" def:"[]"`
}

// Notice is a hint, warning or critical message of the engine.
type Notice struct {
	Code     string   `json:"code"`
	Severity Severity `json:"severity"`
	Message  string   `json:"message"`
	RuleID   *string  `json:"rule_id" def:"null"`
}

// VariantSummary summarises a design variant with its material cost.
type VariantSummary struct {
	Key          string           `json:"key"`
	Name         string           `json:"name"`
	Description  string           `json:"description"`
	Overrides    Dict[ParamValue] `json:"overrides"`
	MaterialCost Money            `json:"material_cost"`
	IsSelected   bool             `json:"is_selected"`
}

// Provenance records which engine, design, catalog and rules produced a result.
type Provenance struct {
	EngineVersion  string    `json:"engine_version"`
	DesignVersion  string    `json:"design_version"`
	CatalogVersion string    `json:"catalog_version"`
	CatalogAsOf    string    `json:"catalog_as_of"`
	Rules          []RuleRef `json:"rules"`
	ComputedAt     DateTime  `json:"computed_at"`
}

// ChoiceSpec is one option of a choice parameter in the UI metadata.
type ChoiceSpec struct {
	Value string `json:"value"`
	Label string `json:"label"`
}

// ParamSpecKind is the kind of a parameter in the UI metadata.
type ParamSpecKind string

func (ParamSpecKind) pyChoices() ([]string, bool) {
	return []string{"length", "count", "angle", "bool", "choice", "number"}, false
}

// ParamSpec is the UI metadata of an adjustable parameter of the design.
type ParamSpec struct {
	Name    string        `json:"name"`
	Label   string        `json:"label"`
	Kind    ParamSpecKind `json:"kind"`
	Min     *float64      `json:"min" def:"null"`
	Max     *float64      `json:"max" def:"null"`
	Options []ChoiceSpec  `json:"options" def:"[]"`
}

// SolidRotation is the rotation of a box solid.
type SolidRotation struct {
	Axis Axis    `json:"axis"`
	Deg  float64 `json:"deg"`
}

// SolidMesh is a triangle mesh in world coordinates for parts that are not plain boxes.
type SolidMesh struct {
	Vertices  [][3]float64 `json:"vertices"`
	Triangles [][3]int     `json:"triangles"`
}

// Solid is a placed part for 3D display (mm; x right, y back, z up; At = min corner). Plain
// boxes are described by Size, At and Rotation; shaped, cut or angled parts carry an
// engine-computed Mesh (then Size/At are their bounding box).
type Solid struct {
	Position int            `json:"position"`
	PartID   string         `json:"part_id"`
	Name     string         `json:"name"`
	Material string         `json:"material"`
	Tone     string         `json:"tone"`
	Size     [3]float64     `json:"size"`
	At       [3]float64     `json:"at"`
	Rotation *SolidRotation `json:"rotation" def:"null"`
	Mesh     *SolidMesh     `json:"mesh" def:"null"`
}

// ConstructionResult is everything the engine derives from the inputs.
type ConstructionResult struct {
	Summary         string            `json:"summary"`
	EffectiveParams Dict[ParamValue]  `json:"effective_params"`
	KeyFigures      Dict[string]      `json:"key_figures"`
	Components      []Component       `json:"components"`
	Bom             []BomLine         `json:"bom"`
	CutList         []CutLine         `json:"cut_list"`
	StockPlan       []StockPlan       `json:"stock_plan"`
	FillLayers      []FillLayer       `json:"fill_layers"`
	Tools           []Tool            `json:"tools"`
	Costs           CostSummary       `json:"costs"`
	Drawings        []Drawing         `json:"drawings"`
	Instructions    []InstructionStep `json:"instructions"`
	Notices         []Notice          `json:"notices"`
	Variants        []VariantSummary  `json:"variants"`
	Provenance      Provenance        `json:"provenance"`
	ParamSpecs      []ParamSpec       `json:"param_specs" def:"[]"`
	Solids          []Solid           `json:"solids" def:"[]"`
}

// Note is free text attached to a project, e.g. an explanation written by the agent.
type Note struct {
	ID        UUID     `json:"id" def:"uuid4"`
	Origin    Origin   `json:"origin"`
	Text      string   `json:"text"`
	CreatedAt DateTime `json:"created_at" def:"now"`
}

// ProjectInputs is the part of the project that commands change.
type ProjectInputs struct {
	Title string `json:"title"`
	// Design is the free-form parametric design; every project is a one-off.
	Design     AssemblyDesign   `json:"design"`
	Params     Dict[ParamValue] `json:"params"`
	VariantKey *string          `json:"variant_key" def:"null"`
	Region     *Region          `json:"region" def:"null"`
	Notes      []Note           `json:"notes" def:"[]"`
	// Prices are unit prices in EUR entered by the user, keyed by BOM item id.
	Prices Dict[decimal.Decimal] `json:"prices" def:"{}"`
}

// Clone returns a copy whose params, notes and prices can be changed independently (the
// design is shared; treat it as immutable).
func (in ProjectInputs) Clone() ProjectInputs {
	out := in
	out.Params = in.Params.Clone()
	out.Notes = append([]Note(nil), in.Notes...)
	out.Prices = in.Prices.Clone()
	return out
}

// ProjectModel is the single source of truth of a construction project.
type ProjectModel struct {
	SchemaVersion int                `json:"schema_version" def:"2" v:"const=2"`
	ID            UUID               `json:"id"`
	Inputs        ProjectInputs      `json:"inputs"`
	Result        ConstructionResult `json:"result"`
}
