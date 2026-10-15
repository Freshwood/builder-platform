package model

// JSON and validation methods of all model types (pydantic-compatible, see codec.go).

// MarshalJSON encodes like model_dump(mode="json").
func (v ChoiceOption) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ChoiceOption) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ChoiceOption) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v DesignParam) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *DesignParam) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v DesignParam) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Rotation) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Rotation) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Rotation) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Repeat) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Repeat) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Repeat) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Shape) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Shape) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Shape) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Cutout) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Cutout) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Cutout) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v PartSpec) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *PartSpec) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v PartSpec) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v HardwareSpec) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *HardwareSpec) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v HardwareSpec) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v JointSpec) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *JointSpec) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v JointSpec) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v DesignStep) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *DesignStep) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v DesignStep) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v DesignVariant) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *DesignVariant) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v DesignVariant) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v AssemblyDesign) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *AssemblyDesign) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v AssemblyDesign) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v RuleRef) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *RuleRef) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v RuleRef) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Profile) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Profile) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Profile) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Component) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Component) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Component) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Money) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Money) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Money) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v BomLine) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *BomLine) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v BomLine) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v CutLine) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *CutLine) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v CutLine) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v StockPlan) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *StockPlan) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v StockPlan) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Tool) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Tool) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Tool) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v FillLayer) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *FillLayer) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v FillLayer) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v CostSummary) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *CostSummary) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v CostSummary) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v InstructionStep) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *InstructionStep) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v InstructionStep) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Notice) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Notice) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Notice) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v VariantSummary) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *VariantSummary) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v VariantSummary) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Provenance) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Provenance) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Provenance) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ChoiceSpec) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ChoiceSpec) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ChoiceSpec) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ParamSpec) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ParamSpec) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ParamSpec) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SolidRotation) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SolidRotation) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SolidRotation) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SolidMesh) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SolidMesh) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SolidMesh) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Solid) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Solid) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Solid) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ConstructionResult) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ConstructionResult) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ConstructionResult) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Note) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Note) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Note) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ProjectInputs) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ProjectInputs) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ProjectInputs) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ProjectModel) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ProjectModel) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ProjectModel) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Rect) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Rect) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Rect) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Line) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Line) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Line) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Dimension) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Dimension) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Dimension) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Label) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Label) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Label) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Polygon) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Polygon) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Polygon) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Callout) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Callout) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Callout) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v LegendEntry) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *LegendEntry) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v LegendEntry) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Drawing) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Drawing) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Drawing) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v CreateProject) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *CreateProject) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v CreateProject) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SetParameters) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SetParameters) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SetParameters) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ChangeParameterBy) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ChangeParameterBy) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ChangeParameterBy) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SelectVariant) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SelectVariant) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SelectVariant) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Rename) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Rename) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Rename) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SetRegion) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SetRegion) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SetRegion) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v AddNote) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *AddNote) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v AddNote) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ReplaceDesign) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ReplaceDesign) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ReplaceDesign) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v SetPrice) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *SetPrice) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v SetPrice) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ReplaceInputs) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ReplaceInputs) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ReplaceInputs) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v Undo) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *Undo) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v Undo) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ValueChange) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ValueChange) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ValueChange) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v QuantityChange) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *QuantityChange) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v QuantityChange) Validate() error { return Validate(v) }

// MarshalJSON encodes like model_dump(mode="json").
func (v ModelDiff) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes and validates like pydantic.
func (v *ModelDiff) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// Validate checks all constraints and model validators.
func (v ModelDiff) Validate() error { return Validate(v) }

// MarshalJSON encodes the value with its Python type.
func (v ParamValue) MarshalJSON() ([]byte, error) { return Encode(v) }

// UnmarshalJSON decodes int, float, str or bool.
func (v *ParamValue) UnmarshalJSON(b []byte) error { return Decode(b, v) }

// MarshalJSON encodes a number or an expression string.
func (x Expr) MarshalJSON() ([]byte, error) { return Encode(x) }

// UnmarshalJSON decodes a number or an expression string.
func (x *Expr) UnmarshalJSON(b []byte) error { return Decode(b, x) }

// MarshalJSON encodes the canonical string form.
func (u UUID) MarshalJSON() ([]byte, error) { return Encode(u) }

// UnmarshalJSON parses the forms accepted by ParseUUID.
func (u *UUID) UnmarshalJSON(b []byte) error { return Decode(b, u) }

// MarshalJSON encodes the pydantic isoformat.
func (dt DateTime) MarshalJSON() ([]byte, error) { return Encode(dt) }

// UnmarshalJSON parses ISO 8601 strings or Unix timestamps.
func (dt *DateTime) UnmarshalJSON(b []byte) error { return Decode(b, dt) }

// MarshalJSON encodes the entries in insertion order.
func (d Dict[V]) MarshalJSON() ([]byte, error) { return Encode(d) }

// UnmarshalJSON decodes an object, keeping the key order.
func (d *Dict[V]) UnmarshalJSON(b []byte) error { return Decode(b, d) }
