package projects

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/freshwood/builder-platform/backend/internal/modules/identity"
	"github.com/freshwood/builder-platform/backend/internal/platform/db/dbtest"
)

func TestRepositoryStoresProjectsAndLog(t *testing.T) {
	ctx := context.Background()
	d := dbtest.Open(t)
	owner, err := identity.NewSQLProvider(d).CreateGuest(ctx)
	if err != nil {
		t.Fatal(err)
	}
	repo := NewSQLRepository(d)
	id := uuid.New()
	model := json.RawMessage(`{"result": {"summary": "Regal – 800 mm"}}`)
	rec := StoredRecord{Seq: 1, Command: json.RawMessage(`{"type":"create_project"}`), Actor: "user", EngineVersion: "e", DesignVersion: "d"}
	if err := repo.Add(ctx, owner.ID, id, "Regal", 2, model, rec); err != nil {
		t.Fatal(err)
	}
	list, err := repo.ListForOwner(ctx, owner.ID)
	if err != nil || len(list) != 1 || list[0].Summary != "Regal – 800 mm" {
		t.Fatalf("list = %+v, %v", list, err)
	}
	rec2 := rec
	rec2.Seq = 2
	rec2.Diff = json.RawMessage(`{"params": []}`)
	if err := repo.Append(ctx, id, "Regal 2", 2, model, rec2); err != nil {
		t.Fatal(err)
	}
	if err := repo.Append(ctx, id, "Regal 3", 2, model, rec2); !errors.Is(err, ErrConcurrentModification) {
		t.Fatalf("duplicate seq: got %v", err)
	}
	log, err := repo.Commands(ctx, id)
	if err != nil || len(log) != 2 || log[1].Diff == nil || log[0].Diff != nil {
		t.Fatalf("log = %+v, %v", log, err)
	}
	got, err := repo.Get(ctx, id)
	if err != nil || got.OwnerID != owner.ID {
		t.Fatalf("get = %+v, %v", got, err)
	}
	if err := repo.Delete(ctx, id); err != nil {
		t.Fatal(err)
	}
	if got, _ := repo.Get(ctx, id); got != nil {
		t.Fatal("project still there")
	}
}
