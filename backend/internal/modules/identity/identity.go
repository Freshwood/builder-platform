// Package identity provides user accounts. Phase I has guest accounts only: a guest gets an
// account on first use, so projects are saved without sign-up. A later OIDC adapter implements
// the same Provider interface.
package identity

import (
	"context"
	"database/sql"
	"errors"

	"github.com/google/uuid"

	"github.com/freshwood/builder-platform/backend/internal/platform/db"
)

// User is an account.
type User struct {
	ID          uuid.UUID
	IsGuest     bool
	DisplayName string
}

// Provider looks up and creates users.
type Provider interface {
	Get(ctx context.Context, id uuid.UUID) (*User, error)
	CreateGuest(ctx context.Context) (*User, error)
}

// SQLProvider stores users in the database.
type SQLProvider struct{ db *db.DB }

// NewSQLProvider returns a provider backed by the users table.
func NewSQLProvider(d *db.DB) *SQLProvider { return &SQLProvider{db: d} }

// Get returns the user or nil when it does not exist.
func (p *SQLProvider) Get(ctx context.Context, id uuid.UUID) (*User, error) {
	var (
		guest bool
		name  sql.NullString
	)
	err := p.db.QueryRowContext(ctx, p.db.Rebind(`SELECT is_guest, display_name FROM users WHERE id = ?`), id.String()).
		Scan(&guest, &name)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &User{ID: id, IsGuest: guest, DisplayName: name.String}, nil
}

// CreateGuest creates a new guest account.
func (p *SQLProvider) CreateGuest(ctx context.Context) (*User, error) {
	user := &User{ID: uuid.New(), IsGuest: true}
	_, err := p.db.ExecContext(ctx, p.db.Rebind(`INSERT INTO users (id, is_guest, created_at) VALUES (?, ?, ?)`),
		user.ID.String(), true, p.db.Stamp(db.Now()))
	return user, err
}
