package db

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func openTest(t *testing.T) *DB {
	t.Helper()
	url := os.Getenv("TEST_DATABASE_URL")
	if url == "" {
		url = "sqlite:///" + filepath.Join(t.TempDir(), "test.db")
	}
	d, err := Open(context.Background(), url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = d.Close() })
	if err := d.Migrate(context.Background()); err != nil {
		t.Fatal(err)
	}
	return d
}

func TestMigrateIsIdempotent(t *testing.T) {
	d := openTest(t)
	if err := d.Migrate(context.Background()); err != nil {
		t.Fatal(err)
	}
	var n int
	if err := d.QueryRow(`SELECT COUNT(*) FROM schema_migrations`).Scan(&n); err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("want 1 applied migration, got %d", n)
	}
}

func TestMemoryDatabase(t *testing.T) {
	d, err := Open(context.Background(), "sqlite:///:memory:")
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	if err := d.Migrate(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestPythonStyleURLs(t *testing.T) {
	d, err := Open(context.Background(), "sqlite+aiosqlite:///"+filepath.Join(t.TempDir(), "x.db"))
	if err != nil {
		t.Fatal(err)
	}
	_ = d.Close()
}

func TestRebind(t *testing.T) {
	d := &DB{Dialect: Postgres}
	if got := d.Rebind("a = ? AND b = ?"); got != "a = $1 AND b = $2" {
		t.Fatal(got)
	}
}
