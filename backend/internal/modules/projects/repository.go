package projects

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"time"

	"github.com/google/uuid"

	"github.com/freshwood/builder-platform/backend/internal/platform/db"
)

// ErrConcurrentModification means another command took the next sequence number first.
var ErrConcurrentModification = errors.New("Das Projekt wurde zwischenzeitlich geändert. Bitte neu laden.")

// StoredRecord is one row of the append-only command log with its JSON documents.
type StoredRecord struct {
	Seq           int
	Command       json.RawMessage
	Actor         string
	EngineVersion string
	DesignVersion string
	LLMTraceID    *string
	Diff          json.RawMessage // nil when no diff was stored
	CreatedAt     time.Time
}

// StoredProject is a project row with its model document.
type StoredProject struct {
	ID        uuid.UUID
	OwnerID   uuid.UUID
	Model     json.RawMessage
	UpdatedAt time.Time
}

// ListItem is the project list entry.
type ListItem struct {
	ID        uuid.UUID
	Title     string
	Summary   string
	UpdatedAt time.Time
}

// Repository stores projects and their command log.
type Repository interface {
	Add(ctx context.Context, owner uuid.UUID, id uuid.UUID, title string, schemaVersion int, model json.RawMessage, record StoredRecord) error
	Get(ctx context.Context, id uuid.UUID) (*StoredProject, error)
	ListForOwner(ctx context.Context, owner uuid.UUID) ([]ListItem, error)
	Append(ctx context.Context, id uuid.UUID, title string, schemaVersion int, model json.RawMessage, record StoredRecord) error
	Commands(ctx context.Context, id uuid.UUID) ([]StoredRecord, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// SQLRepository implements Repository on SQLite and PostgreSQL.
type SQLRepository struct{ db *db.DB }

// NewSQLRepository returns a repository on the given database.
func NewSQLRepository(d *db.DB) *SQLRepository { return &SQLRepository{db: d} }

func (r *SQLRepository) insertRecord(ctx context.Context, tx *sql.Tx, id uuid.UUID, rec StoredRecord, now time.Time) error {
	var diff any
	if rec.Diff != nil {
		diff = db.JSON(rec.Diff)
	}
	_, err := tx.ExecContext(ctx, r.db.Rebind(`INSERT INTO project_commands
		(project_id, seq, command, actor, llm_trace_id, engine_version, design_version, diff, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`),
		id.String(), rec.Seq, db.JSON(rec.Command), rec.Actor, rec.LLMTraceID, rec.EngineVersion,
		rec.DesignVersion, diff, r.db.Stamp(now))
	return err
}

// Add stores a new project with its first log entry.
func (r *SQLRepository) Add(ctx context.Context, owner, id uuid.UUID, title string, schemaVersion int, model json.RawMessage, rec StoredRecord) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	now := db.Now()
	if _, err := tx.ExecContext(ctx, r.db.Rebind(`INSERT INTO projects
		(id, owner_id, title, schema_version, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)`),
		id.String(), owner.String(), title, schemaVersion, db.JSON(model), r.db.Stamp(now), r.db.Stamp(now)); err != nil {
		return err
	}
	if err := r.insertRecord(ctx, tx, id, rec, now); err != nil {
		return err
	}
	return tx.Commit()
}

// Get returns the project or nil.
func (r *SQLRepository) Get(ctx context.Context, id uuid.UUID) (*StoredProject, error) {
	var (
		owner   string
		model   db.NullableJSON
		updated db.Time
	)
	err := r.db.QueryRowContext(ctx, r.db.Rebind(`SELECT owner_id, model, updated_at FROM projects WHERE id = ?`), id.String()).
		Scan(&owner, &model, &updated)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	ownerID, err := uuid.Parse(owner)
	if err != nil {
		return nil, err
	}
	return &StoredProject{ID: id, OwnerID: ownerID, Model: json.RawMessage(model), UpdatedAt: updated.Time}, nil
}

// ListForOwner lists the owner's projects, most recently changed first. The summary is read in
// the database instead of loading every full model document.
func (r *SQLRepository) ListForOwner(ctx context.Context, owner uuid.UUID) ([]ListItem, error) {
	summary := `json_extract(model, '$.result.summary')`
	if r.db.Dialect == db.Postgres {
		summary = `model->'result'->>'summary'`
	}
	rows, err := r.db.QueryContext(ctx, r.db.Rebind(`SELECT id, title, `+summary+`, updated_at FROM projects
		WHERE owner_id = ? ORDER BY updated_at DESC, created_at DESC`), owner.String())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ListItem{}
	for rows.Next() {
		var (
			id, title string
			text      sql.NullString
			updated   db.Time
		)
		if err := rows.Scan(&id, &title, &text, &updated); err != nil {
			return nil, err
		}
		pid, err := uuid.Parse(id)
		if err != nil {
			return nil, err
		}
		items = append(items, ListItem{ID: pid, Title: title, Summary: text.String, UpdatedAt: updated.Time})
	}
	return items, rows.Err()
}

// Append stores the new model and its log entry atomically. A concurrent request that took the
// same sequence number makes the unique constraint roll back the whole transaction.
func (r *SQLRepository) Append(ctx context.Context, id uuid.UUID, title string, schemaVersion int, model json.RawMessage, rec StoredRecord) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	now := db.Now()
	res, err := tx.ExecContext(ctx, r.db.Rebind(`UPDATE projects SET title = ?, schema_version = ?, model = ?, updated_at = ? WHERE id = ?`),
		title, schemaVersion, db.JSON(model), r.db.Stamp(now), id.String())
	if err != nil {
		return err
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return sql.ErrNoRows
	}
	if err := r.insertRecord(ctx, tx, id, rec, now); err != nil {
		if db.IsUniqueViolation(err) {
			return ErrConcurrentModification
		}
		return err
	}
	if err := tx.Commit(); err != nil {
		if db.IsUniqueViolation(err) {
			return ErrConcurrentModification
		}
		return err
	}
	return nil
}

// Commands returns the full log of a project ordered by sequence number.
func (r *SQLRepository) Commands(ctx context.Context, id uuid.UUID) ([]StoredRecord, error) {
	rows, err := r.db.QueryContext(ctx, r.db.Rebind(`SELECT seq, command, actor, llm_trace_id, engine_version,
		design_version, diff, created_at FROM project_commands WHERE project_id = ? ORDER BY seq`), id.String())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []StoredRecord
	for rows.Next() {
		var (
			rec     StoredRecord
			command db.NullableJSON
			diff    db.NullableJSON
			trace   sql.NullString
			created db.Time
		)
		if err := rows.Scan(&rec.Seq, &command, &rec.Actor, &trace, &rec.EngineVersion, &rec.DesignVersion, &diff, &created); err != nil {
			return nil, err
		}
		rec.Command = json.RawMessage(command)
		if diff != nil {
			rec.Diff = json.RawMessage(diff)
		}
		if trace.Valid {
			rec.LLMTraceID = &trace.String
		}
		rec.CreatedAt = created.Time
		out = append(out, rec)
	}
	return out, rows.Err()
}

// Delete removes the project and its log (agent runs cascade in the database).
func (r *SQLRepository) Delete(ctx context.Context, id uuid.UUID) error {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	for _, q := range []string{
		`DELETE FROM project_commands WHERE project_id = ?`,
		`DELETE FROM agent_runs WHERE project_id = ?`,
		`DELETE FROM projects WHERE id = ?`,
	} {
		if _, err := tx.ExecContext(ctx, r.db.Rebind(q), id.String()); err != nil {
			return err
		}
	}
	return tx.Commit()
}
