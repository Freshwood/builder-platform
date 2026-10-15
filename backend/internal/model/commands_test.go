package model_test

import (
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"

	"github.com/freshwood/builder-platform/backend/internal/model"
	"github.com/shopspring/decimal"
)

// Port of packages/construction-model/tests/test_commands.py.

func design(t *testing.T) model.AssemblyDesign {
	t.Helper()
	var d model.AssemblyDesign
	err := json.Unmarshal([]byte(`{
		"object_type": "Brett",
		"summary": "Brett",
		"params": [{"name": "width_mm", "label": "Breite", "kind": "length", "default": 800, "min": 300, "max": 2000}],
		"parts": [{"id": "board", "name": "Brett", "material": "m", "size": ["width_mm", 100, 18], "at": [0, 0, 0]}]
	}`), &d)
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func params(pairs ...any) model.Dict[model.ParamValue] {
	var d model.Dict[model.ParamValue]
	for i := 0; i < len(pairs); i += 2 {
		var v model.ParamValue
		switch x := pairs[i+1].(type) {
		case int:
			v = model.IntValue(int64(x))
		case float64:
			v = model.FloatValue(x)
		case string:
			v = model.StringValue(x)
		case bool:
			v = model.BoolValue(x)
		}
		d.Set(pairs[i].(string), v)
	}
	return d
}

func created(t *testing.T) model.ProjectInputs {
	t.Helper()
	in, err := model.ApplyToInputs(nil, model.CreateProject{Title: "Beet", Design: design(t), Params: params("width_mm", 1000)}, nil)
	if err != nil {
		t.Fatal(err)
	}
	return in
}

func apply(t *testing.T, in model.ProjectInputs, c model.Command, overrides map[string]model.Dict[model.ParamValue]) model.ProjectInputs {
	t.Helper()
	out, err := model.ApplyToInputs(&in, c, overrides)
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func isCommandError(err error) bool {
	var ce *model.CommandError
	return errors.As(err, &ce)
}

func TestCreateRequiresEmptyProject(t *testing.T) {
	in := created(t)
	_, err := model.ApplyToInputs(&in, model.CreateProject{Title: "x", Design: design(t)}, nil)
	if !isCommandError(err) {
		t.Fatalf("want CommandError, got %v", err)
	}
}

func TestFirstCommandMustCreate(t *testing.T) {
	if _, err := model.ApplyToInputs(nil, model.Rename{Title: "x"}, nil); !isCommandError(err) {
		t.Fatalf("want CommandError, got %v", err)
	}
}

func TestChangeParameterByIsRelative(t *testing.T) {
	in := apply(t, created(t), model.ChangeParameterBy{Name: "width_mm", Delta: 500}, nil)
	v, _ := in.Params.Get("width_mm")
	if i, ok := v.Int(); !ok || i != 1500 {
		t.Fatalf("width_mm = %v", v)
	}
	// Float parameters stay floats; a missing value starts from the design default.
	in = apply(t, in, model.SetParameters{Values: params("width_mm", 2.5)}, nil)
	in = apply(t, in, model.ChangeParameterBy{Name: "width_mm", Delta: 1}, nil)
	if v, _ := in.Params.Get("width_mm"); v.Kind() != model.FloatKind || v.PyStr() != "3.5" {
		t.Fatalf("width_mm = %v", v)
	}
	in.Params.Delete("width_mm")
	in = apply(t, in, model.ChangeParameterBy{Name: "width_mm", Delta: -100}, nil)
	if v, _ := in.Params.Get("width_mm"); v.PyStr() != "700" {
		t.Fatalf("width_mm = %v", v)
	}
}

func TestChangeParameterByRejectsNonNumeric(t *testing.T) {
	in := apply(t, created(t), model.SetParameters{Values: params("wood", "larch", "flag", true)}, nil)
	for _, name := range []string{"wood", "missing", "flag"} {
		if _, err := model.ApplyToInputs(&in, model.ChangeParameterBy{Name: name, Delta: 1}, nil); !isCommandError(err) {
			t.Fatalf("%s: want CommandError, got %v", name, err)
		}
	}
}

func TestSelectVariantAppliesOverrides(t *testing.T) {
	overrides := map[string]model.Dict[model.ParamValue]{"durable": params("wood", "larch")}
	in := apply(t, created(t), model.SelectVariant{VariantKey: "durable"}, overrides)
	if in.VariantKey == nil || *in.VariantKey != "durable" {
		t.Fatalf("variant_key = %v", in.VariantKey)
	}
	if v, _ := in.Params.Get("wood"); v.PyStr() != "larch" {
		t.Fatalf("wood = %v", v)
	}
	if _, err := model.ApplyToInputs(&in, model.SelectVariant{VariantKey: "nope"}, overrides); !isCommandError(err) {
		t.Fatalf("want CommandError, got %v", err)
	}
}

func TestAddNoteKeepsOrigin(t *testing.T) {
	note := model.New[model.AddNote]()
	note.Text = "Erklärung"
	note.Origin = model.OriginAI
	in := apply(t, created(t), note, nil)
	if in.Notes[0].Origin != model.OriginAI || in.Notes[0].ID != note.NoteID {
		t.Fatalf("notes = %+v", in.Notes)
	}
	if model.New[model.AddNote]().Origin != model.OriginUser {
		t.Fatal("default origin must be user")
	}
}

func TestEffectiveCommandsResolvesUndoWithStackSemantics(t *testing.T) {
	d := design(t)
	log := []model.LogEntry[int]{
		{1, model.CreateProject{Title: "t", Design: d}},
		{2, model.Rename{Title: "a"}},
		{3, model.Rename{Title: "b"}},
		{4, model.Undo{}},
		{5, model.Rename{Title: "c"}},
		{6, model.Undo{}},
		{7, model.Undo{}},
	}
	eff, err := model.EffectiveCommands(log)
	if err != nil {
		t.Fatal(err)
	}
	if len(eff) != 1 || eff[0].Key != 1 {
		t.Fatalf("effective = %+v", eff)
	}
}

func TestCreateCannotBeUndone(t *testing.T) {
	d := design(t)
	_, err := model.EffectiveCommands([]model.LogEntry[int]{{0, model.CreateProject{Title: "t", Design: d}}, {1, model.Undo{}}})
	if !isCommandError(err) {
		t.Fatalf("want CommandError, got %v", err)
	}
	if model.CanUndo([]model.Command{model.CreateProject{Title: "t", Design: d}}) {
		t.Fatal("create alone must not be undoable")
	}
	if !model.CanUndo([]model.Command{model.CreateProject{Title: "t", Design: d}, model.Rename{Title: "x"}}) {
		t.Fatal("rename must be undoable")
	}
}

func TestCommandJSONRoundtrip(t *testing.T) {
	cmd, err := model.UnmarshalCommand([]byte(`{"type": "change_parameter_by", "name": "w", "delta": 5}`))
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := cmd.(model.ChangeParameterBy); !ok {
		t.Fatalf("got %T", cmd)
	}
	data, err := model.MarshalCommand(cmd)
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != `{"type":"change_parameter_by","name":"w","delta":5}` {
		t.Fatalf("encoded %s", data)
	}
	again, err := model.UnmarshalCommand(data)
	if err != nil || !reflect.DeepEqual(again, cmd) {
		t.Fatalf("roundtrip: %v %v", again, err)
	}
	// Every command type survives a roundtrip.
	note := model.New[model.AddNote]()
	note.Text = "x"
	price := decimal.RequireFromString("7.49")
	region := model.RegionBY
	in := created(t)
	for _, c := range []model.Command{
		model.CreateProject{Title: "t", Design: design(t), Region: &region},
		model.SetParameters{Values: params("a", 1, "b", 1.0, "c", "x", "d", false)},
		model.SelectVariant{VariantKey: "k"},
		model.Rename{Title: "n"},
		model.SetRegion{},
		note,
		model.ReplaceDesign{Design: design(t)},
		model.SetPrice{ItemID: "glue", UnitPrice: &price},
		model.ReplaceInputs{Inputs: in},
		model.Undo{},
	} {
		data, err := model.MarshalCommand(c)
		if err != nil {
			t.Fatal(err)
		}
		back, err := model.UnmarshalCommand(data)
		if err != nil {
			t.Fatalf("%s: %v", data, err)
		}
		again, _ := model.MarshalCommand(back)
		if string(again) != string(data) {
			t.Fatalf("roundtrip differs:\n%s\n%s", data, again)
		}
	}
}

func TestEditCommandRejectsCreate(t *testing.T) {
	_, err := model.UnmarshalEditCommand([]byte(`{"type": "undo"}`))
	if err == nil || !strings.Contains(err.Error(), "does not match any of the expected tags: 'set_parameters'") {
		t.Fatalf("got %v", err)
	}
	c, err := model.UnmarshalEditCommand([]byte(`{"type": "rename", "title": "x"}`))
	if err != nil || c.(model.Rename).Title != "x" {
		t.Fatalf("got %v %v", c, err)
	}
}

func TestSetPriceSetsAndClearsUserPrice(t *testing.T) {
	price := decimal.RequireFromString("7.49")
	in := apply(t, created(t), model.SetPrice{ItemID: "glue_d3_750", UnitPrice: &price}, nil)
	if got, _ := in.Prices.Get("glue_d3_750"); in.Prices.Len() != 1 || !got.Equal(price) {
		t.Fatalf("prices = %v", in.Prices.Map())
	}
	cleared := apply(t, in, model.SetPrice{ItemID: "glue_d3_750"}, nil)
	if cleared.Prices.Len() != 0 {
		t.Fatalf("prices = %v", cleared.Prices.Map())
	}
	if in.Prices.Len() != 1 {
		t.Fatal("ApplyToInputs must not modify its input")
	}
}

func TestSetPriceRejectsNegativePrices(t *testing.T) {
	price := decimal.RequireFromString("-1")
	err := model.SetPrice{ItemID: "glue_d3_750", UnitPrice: &price}.Validate()
	if err == nil || !strings.Contains(err.Error(), "greater than or equal to 0") {
		t.Fatalf("got %v", err)
	}
}

func TestReplaceDesignKeepsValidParamsAndUserNotes(t *testing.T) {
	in := apply(t, created(t), model.SetParameters{Values: params("width_mm", 2500, "gone", 1)}, nil)
	ai := model.New[model.AddNote]()
	ai.Text, ai.Origin = "KI", model.OriginAI
	user := model.New[model.AddNote]()
	user.Text = "ich"
	in = apply(t, apply(t, in, ai, nil), user, nil)
	key := "v"
	in.VariantKey = &key
	out := apply(t, in, model.ReplaceDesign{Design: design(t)}, nil)
	if out.Params.Len() != 0 {
		// 2500 is above max 2000, "gone" is not declared.
		t.Fatalf("params = %v", out.Params.Map())
	}
	if len(out.Notes) != 1 || out.Notes[0].Text != "ich" || out.VariantKey != nil {
		t.Fatalf("notes = %+v variant = %v", out.Notes, out.VariantKey)
	}
	in = apply(t, in, model.SetParameters{Values: params("width_mm", 2000.0)}, nil)
	out = apply(t, in, model.ReplaceDesign{Design: design(t)}, nil)
	if out.Params.Len() != 1 {
		t.Fatalf("params = %v", out.Params.Map())
	}
}
