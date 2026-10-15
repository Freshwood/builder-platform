package model

import (
	"sort"

	"github.com/shopspring/decimal"
)

// ValueChange is a changed parameter or key figure; nil means absent on that side.
type ValueChange struct {
	Name   string      `json:"name"`
	Before *ParamValue `json:"before"`
	After  *ParamValue `json:"after"`
}

// QuantityChange is a changed BOM quantity.
type QuantityChange struct {
	ItemID string          `json:"item_id"`
	Name   string          `json:"name"`
	Unit   string          `json:"unit"`
	Before decimal.Decimal `json:"before"`
	After  decimal.Decimal `json:"after"`
}

// ModelDiff is the human- and machine-readable difference between two engine results.
type ModelDiff struct {
	Params             []ValueChange       `json:"params"`
	KeyFigures         []ValueChange       `json:"key_figures"`
	Quantities         []QuantityChange    `json:"quantities"`
	MaterialCostBefore *[2]decimal.Decimal `json:"material_cost_before"`
	MaterialCostAfter  [2]decimal.Decimal  `json:"material_cost_after"`
}

// The diff models do not forbid extra fields in Python.
func (ValueChange) allowExtra()    {}
func (QuantityChange) allowExtra() {}
func (ModelDiff) allowExtra()      {}

// IsEmpty reports a diff without parameter, key figure or quantity changes.
func (d ModelDiff) IsEmpty() bool {
	return len(d.Params) == 0 && len(d.KeyFigures) == 0 && len(d.Quantities) == 0
}

func sortedUnion(a, b []string) []string {
	set := map[string]bool{}
	for _, k := range a {
		set[k] = true
	}
	for _, k := range b {
		set[k] = true
	}
	out := make([]string, 0, len(set))
	for k := range set {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func changes(before, after Dict[ParamValue]) []ValueChange {
	out := []ValueChange{}
	for _, key := range sortedUnion(before.Keys(), after.Keys()) {
		old, inOld := before.Get(key)
		nw, inNew := after.Get(key)
		var same bool
		switch {
		case inOld && inNew:
			same = old.Equal(nw)
		default:
			same = inOld == inNew
		}
		if same {
			continue
		}
		vc := ValueChange{Name: key}
		if inOld {
			o := old
			vc.Before = &o
		}
		if inNew {
			n := nw
			vc.After = &n
		}
		out = append(out, vc)
	}
	return out
}

func stringDict(d Dict[string]) Dict[ParamValue] {
	var out Dict[ParamValue]
	for k, v := range d.All() {
		out.Set(k, StringValue(v))
	}
	return out
}

// DiffResults compares two results; before is nil for the first build.
func DiffResults(before *ConstructionResult, after ConstructionResult) ModelDiff {
	oldLines := map[string]BomLine{}
	var oldIDs []string
	if before != nil {
		for _, l := range before.Bom {
			if _, dup := oldLines[l.ItemID]; !dup {
				oldIDs = append(oldIDs, l.ItemID)
			}
			oldLines[l.ItemID] = l
		}
	}
	newLines := map[string]BomLine{}
	var newIDs []string
	for _, l := range after.Bom {
		if _, dup := newLines[l.ItemID]; !dup {
			newIDs = append(newIDs, l.ItemID)
		}
		newLines[l.ItemID] = l
	}
	quantities := []QuantityChange{}
	for _, id := range sortedUnion(oldIDs, newIDs) {
		old, inOld := oldLines[id]
		nw, inNew := newLines[id]
		oldQty, newQty := decimal.Zero, decimal.Zero
		if inOld {
			oldQty = old.Quantity
		}
		if inNew {
			newQty = nw.Quantity
		}
		if oldQty.Equal(newQty) {
			continue
		}
		ref := old
		if inNew {
			ref = nw
		}
		quantities = append(quantities, QuantityChange{ItemID: id, Name: ref.Name, Unit: ref.Unit, Before: oldQty, After: newQty})
	}
	diff := ModelDiff{
		Quantities:        quantities,
		MaterialCostAfter: [2]decimal.Decimal{after.Costs.Material.Min, after.Costs.Material.Max},
	}
	if before != nil {
		diff.Params = changes(before.EffectiveParams, after.EffectiveParams)
		diff.KeyFigures = changes(stringDict(before.KeyFigures), stringDict(after.KeyFigures))
		diff.MaterialCostBefore = &[2]decimal.Decimal{before.Costs.Material.Min, before.Costs.Material.Max}
	} else {
		diff.Params = changes(Dict[ParamValue]{}, after.EffectiveParams)
		diff.KeyFigures = changes(Dict[ParamValue]{}, stringDict(after.KeyFigures))
	}
	return diff
}
