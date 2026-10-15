// Package dbtest opens migrated databases for tests.
package dbtest

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/freshwood/builder-platform/backend/internal/platform/db"
)

// Open returns a migrated database: TEST_DATABASE_URL (PostgreSQL, `task test:pg`) when set,
// otherwise a fresh SQLite file in a temporary directory.
func Open(t testing.TB) *db.DB {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		url = "sqlite:///" + filepath.Join(t.TempDir(), "test.db")
	}
	d, err := db.Open(context.Background(), url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = d.Close() })
	if err := d.Migrate(context.Background()); err != nil {
		t.Fatal(err)
	}
	if d.Dialect == db.Postgres {
		// Shared database: start every test from empty tables.
		if _, err := d.Exec(`TRUNCATE agent_runs, project_commands, projects, users CASCADE`); err != nil {
			t.Fatal(err)
		}
	}
	return d
}
