package conversations

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/google/uuid"

	"github.com/freshwood/builder-platform/backend/internal/modules/identity"
	"github.com/freshwood/builder-platform/backend/internal/platform/db/dbtest"
)

func TestRunsBecomeTheProjectChat(t *testing.T) {
	ctx := context.Background()
	d := dbtest.Open(t)
	owner, err := identity.NewSQLProvider(d).CreateGuest(ctx)
	if err != nil {
		t.Fatal(err)
	}
	projectID := uuid.New()
	if _, err := d.Exec(d.Rebind(`INSERT INTO projects (id, owner_id, title, schema_version, model, created_at, updated_at)
		VALUES (?, ?, 'x', 2, '{}', ?, ?)`), projectID.String(), owner.ID.String(), d.Stamp(dbNow()), d.Stamp(dbNow())); err != nil {
		t.Fatal(err)
	}
	s := NewService(d)
	chat := "chat-1"
	first := Run{TraceID: "t1", OwnerID: owner.ID, ChatID: &chat, Status: StatusCompleted, Model: "m", PromptVersion: "v",
		UIMessages: []json.RawMessage{json.RawMessage(`{"role":"user","text":"Frage"}`)}, ModelMessages: json.RawMessage(`[{"m":1}]`)}
	if err := s.Record(ctx, first); err != nil {
		t.Fatal(err)
	}
	second := first
	second.TraceID = "t2"
	second.ProjectID = &projectID
	second.UIMessages = []json.RawMessage{json.RawMessage(`{"role":"user","text":"Regal"}`)}
	second.ModelMessages = json.RawMessage(`[{"m":2}]`)
	if err := s.Record(ctx, second); err != nil {
		t.Fatal(err)
	}
	failed := second
	failed.TraceID = "t3"
	failed.Status = StatusFailed
	failed.ModelMessages = nil
	if err := s.Record(ctx, failed); err != nil {
		t.Fatal(err)
	}
	messages, err := s.Chat(ctx, owner.ID, projectID)
	if err != nil || len(messages) != 3 {
		t.Fatalf("chat = %s, %v", messages, err)
	}
	history, err := s.History(ctx, owner.ID, &chat, &projectID)
	if err != nil || len(history) != 2 || string(history[0]) != `{"m":1}` {
		t.Fatalf("history = %s, %v", history, err)
	}
}
