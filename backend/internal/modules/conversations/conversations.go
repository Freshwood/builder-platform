// Package conversations stores agent runs completely: they cost money and are the provenance of
// AI results (ADR-0005). The chat of a project is rebuilt from its runs, so it survives reloads.
package conversations

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/google/uuid"

	"github.com/freshwood/builder-platform/backend/internal/platform/db"
)

// Run statuses.
const (
	StatusCompleted = "completed"
	StatusFailed    = "failed"
	StatusCancelled = "cancelled"
)

// HistoryMaxRuns limits the history sent to the model: older turns add little but cost tokens.
const HistoryMaxRuns = 20

// Run is one assistant turn with everything it produced.
type Run struct {
	TraceID            string
	OwnerID            uuid.UUID
	ChatID             *string
	ProjectID          *uuid.UUID
	Status             string
	Model              string
	PromptVersion      string
	UIMessages         []json.RawMessage
	ModelMessages      json.RawMessage // nil unless the run completed
	DesignAttempts     []json.RawMessage
	Usage              json.RawMessage
	Error              *string
	PromptFingerprint  *string
	SafetyRulesVersion *string
	ModelRole          *string
	RoutingReason      *string
	DurationMS         *int
}

// Service stores and reads agent runs.
type Service struct{ db *db.DB }

// NewService returns a service on the given database.
func NewService(d *db.DB) *Service { return &Service{db: d} }

func jsonList(items []json.RawMessage) []byte {
	if items == nil {
		items = []json.RawMessage{}
	}
	raw, _ := json.Marshal(items)
	return raw
}

func nullable(raw json.RawMessage) any {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	return db.JSON(raw)
}

func str(s *string) any {
	if s == nil {
		return nil
	}
	return *s
}

// Record stores a finished run and attaches the chat's earlier project-less turns to its project.
func (s *Service) Record(ctx context.Context, run Run) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	var projectID, duration any
	if run.ProjectID != nil {
		projectID = run.ProjectID.String()
	}
	if run.DurationMS != nil {
		duration = *run.DurationMS
	}
	var errText *string
	if run.Error != nil {
		e := *run.Error
		if len(e) > 2000 {
			e = strings.ToValidUTF8(e[:2000], "")
		}
		errText = &e
	}
	_, err = tx.ExecContext(ctx, s.db.Rebind(`INSERT INTO agent_runs (id, trace_id, owner_id, chat_id, project_id,
		status, model, prompt_version, prompt_fingerprint, safety_rules_version, model_role, routing_reason,
		duration_ms, ui_messages, model_messages, design_attempts, usage, error, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`),
		uuid.New().String(), run.TraceID, run.OwnerID.String(), str(run.ChatID), projectID, run.Status, run.Model,
		run.PromptVersion, str(run.PromptFingerprint), str(run.SafetyRulesVersion), str(run.ModelRole),
		str(run.RoutingReason), duration, db.JSON(jsonList(run.UIMessages)), nullable(run.ModelMessages),
		db.JSON(jsonList(run.DesignAttempts)), nullable(run.Usage), str(errText), s.db.Stamp(db.Now()))
	if err != nil {
		return err
	}
	if run.ProjectID != nil && run.ChatID != nil {
		// Questions asked before the first project existed belong to its chat, too.
		if _, err := tx.ExecContext(ctx, s.db.Rebind(`UPDATE agent_runs SET project_id = ?
			WHERE owner_id = ? AND chat_id = ? AND project_id IS NULL`),
			run.ProjectID.String(), run.OwnerID.String(), *run.ChatID); err != nil {
			return err
		}
	}
	return tx.Commit()
}

// Chat returns the UI messages of all turns about a project, oldest first.
func (s *Service) Chat(ctx context.Context, owner, project uuid.UUID) ([]json.RawMessage, error) {
	rows, err := s.db.QueryContext(ctx, s.db.Rebind(`SELECT ui_messages FROM agent_runs
		WHERE owner_id = ? AND project_id = ? ORDER BY created_at, id`), owner.String(), project.String())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []json.RawMessage{}
	for rows.Next() {
		var raw db.NullableJSON
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		var messages []json.RawMessage
		if err := json.Unmarshal(raw, &messages); err != nil {
			return nil, err
		}
		out = append(out, messages...)
	}
	return out, rows.Err()
}

// History returns the model messages of the latest completed turns of a chat or project, oldest
// run first. This is the trusted history for the next turn: the browser only sends its new message.
func (s *Service) History(ctx context.Context, owner uuid.UUID, chatID *string, project *uuid.UUID) ([]json.RawMessage, error) {
	var (
		scopes []string
		args   = []any{owner.String(), StatusCompleted}
	)
	if chatID != nil {
		scopes = append(scopes, "chat_id = ?")
		args = append(args, *chatID)
	}
	if project != nil {
		scopes = append(scopes, "project_id = ?")
		args = append(args, project.String())
	}
	if len(scopes) == 0 {
		return nil, nil
	}
	args = append(args, HistoryMaxRuns)
	rows, err := s.db.QueryContext(ctx, s.db.Rebind(`SELECT model_messages FROM agent_runs
		WHERE owner_id = ? AND status = ? AND model_messages IS NOT NULL AND (`+strings.Join(scopes, " OR ")+`)
		ORDER BY created_at DESC, id DESC LIMIT ?`), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var runs [][]byte
	for rows.Next() {
		var raw db.NullableJSON
		if err := rows.Scan(&raw); err != nil {
			return nil, err
		}
		runs = append(runs, raw)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	var out []json.RawMessage
	for i := len(runs) - 1; i >= 0; i-- {
		if len(runs[i]) == 0 || string(runs[i]) == "null" {
			continue
		}
		var messages []json.RawMessage
		if err := json.Unmarshal(runs[i], &messages); err != nil {
			return nil, err
		}
		out = append(out, messages...)
	}
	return out, nil
}
