// Package db opens the database (SQLite or PostgreSQL), runs the embedded migrations and offers
// small helpers that hide the differences between both dialects.
package db

import (
	"context"
	"database/sql"
	"database/sql/driver"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib" // registers the "pgx" driver
	_ "modernc.org/sqlite"             // registers the "sqlite" driver
)

//go:embed migrations
var migrations embed.FS

// Dialect names the SQL flavour of a database.
type Dialect string

const (
	SQLite   Dialect = "sqlite"
	Postgres Dialect = "postgres"
)

// DB wraps *sql.DB with its dialect.
type DB struct {
	*sql.DB
	Dialect Dialect
}

// Open connects to DATABASE_URL. Accepted forms: `sqlite:///relative/or/absolute.db`,
// `sqlite:///:memory:`, `postgres://…` and `postgresql://…`. The driver suffixes of the former
// Python settings (`sqlite+aiosqlite`, `postgresql+psycopg`) are accepted as well.
func Open(ctx context.Context, url string) (*DB, error) {
	scheme, rest, ok := strings.Cut(url, "://")
	if !ok {
		return nil, fmt.Errorf("DATABASE_URL: ungültig: %q", url)
	}
	scheme, _, _ = strings.Cut(scheme, "+")
	switch scheme {
	case "sqlite":
		path := strings.TrimPrefix(rest, "/")
		if path == "" {
			path = ":memory:"
		}
		dsn := "file:" + path
		if path != ":memory:" {
			if dir := filepath.Dir(path); dir != "." {
				if err := os.MkdirAll(dir, 0o755); err != nil {
					return nil, err
				}
			}
		}
		dsn += "?_pragma=foreign_keys(1)&_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)"
		conn, err := sql.Open("sqlite", dsn)
		if err != nil {
			return nil, err
		}
		// SQLite allows one writer; a single connection also keeps :memory: databases shared.
		conn.SetMaxOpenConns(1)
		return ping(ctx, &DB{DB: conn, Dialect: SQLite})
	case "postgres", "postgresql":
		conn, err := sql.Open("pgx", "postgres://"+rest)
		if err != nil {
			return nil, err
		}
		conn.SetMaxOpenConns(20)
		conn.SetConnMaxIdleTime(5 * time.Minute)
		return ping(ctx, &DB{DB: conn, Dialect: Postgres})
	}
	return nil, fmt.Errorf("DATABASE_URL: unbekanntes Schema %q", scheme)
}

func ping(ctx context.Context, d *DB) (*DB, error) {
	if err := d.PingContext(ctx); err != nil {
		_ = d.Close()
		return nil, err
	}
	return d, nil
}

// Rebind turns `?` placeholders into `$1, $2, …` for PostgreSQL.
func (d *DB) Rebind(query string) string {
	if d.Dialect != Postgres {
		return query
	}
	var b strings.Builder
	n := 0
	for _, r := range query {
		if r == '?' {
			n++
			b.WriteString("$" + strconv.Itoa(n))
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

// Migrate applies every embedded migration of the dialect that has not run yet.
func (d *DB) Migrate(ctx context.Context) error {
	if _, err := d.ExecContext(ctx,
		`CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)`,
	); err != nil {
		return fmt.Errorf("schema_migrations: %w", err)
	}
	dir := "migrations/" + string(d.Dialect)
	entries, err := fs.ReadDir(migrations, dir)
	if err != nil {
		return err
	}
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".sql") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		version := strings.TrimSuffix(name, ".sql")
		var found string
		err := d.QueryRowContext(ctx, d.Rebind(`SELECT version FROM schema_migrations WHERE version = ?`), version).Scan(&found)
		if err == nil {
			continue
		}
		if !errors.Is(err, sql.ErrNoRows) {
			return err
		}
		body, err := migrations.ReadFile(dir + "/" + name)
		if err != nil {
			return err
		}
		tx, err := d.BeginTx(ctx, nil)
		if err != nil {
			return err
		}
		if _, err := tx.ExecContext(ctx, string(body)); err != nil {
			_ = tx.Rollback()
			return fmt.Errorf("migration %s: %w", name, err)
		}
		if _, err := tx.ExecContext(ctx, d.Rebind(`INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)`),
			version, Now().Format(TimeLayout)); err != nil {
			_ = tx.Rollback()
			return err
		}
		if err := tx.Commit(); err != nil {
			return err
		}
	}
	return nil
}

// TimeLayout stores timestamps as fixed-width UTC text in SQLite, so text order is time order.
const TimeLayout = "2006-01-02T15:04:05.000000Z07:00"

// Now is the current time in UTC with microsecond resolution (what both databases keep).
func Now() time.Time { return time.Now().UTC().Truncate(time.Microsecond) }

// Time scans timestamps from both dialects: SQLite stores RFC 3339 text, PostgreSQL timestamptz.
type Time struct{ time.Time }

// Scan implements sql.Scanner.
func (t *Time) Scan(src any) error {
	switch v := src.(type) {
	case time.Time:
		t.Time = v.UTC()
	case string:
		parsed, err := time.Parse(time.RFC3339Nano, v)
		if err != nil {
			return err
		}
		t.Time = parsed
	case []byte:
		return t.Scan(string(v))
	case nil:
		t.Time = time.Time{}
	default:
		return fmt.Errorf("db.Time: unsupported type %T", src)
	}
	return nil
}

// Stamp converts a time for writing: text for SQLite, time.Time for PostgreSQL.
func (d *DB) Stamp(t time.Time) driver.Value {
	if d.Dialect == SQLite {
		return t.UTC().Format(TimeLayout)
	}
	return t.UTC()
}

// JSON converts a JSON document for writing: text for SQLite, text cast by PostgreSQL to jsonb.
func JSON(raw []byte) any {
	if raw == nil {
		return nil
	}
	return string(raw)
}

// NullableJSON scans a JSON column that may be NULL into raw bytes (nil for NULL).
type NullableJSON []byte

// Scan implements sql.Scanner.
func (j *NullableJSON) Scan(src any) error {
	switch v := src.(type) {
	case nil:
		*j = nil
	case string:
		*j = []byte(v)
	case []byte:
		*j = append((*j)[:0], v...)
	default:
		return fmt.Errorf("db.NullableJSON: unsupported type %T", src)
	}
	return nil
}

// IsUniqueViolation reports whether err is a unique-constraint violation in either dialect.
func IsUniqueViolation(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	return strings.Contains(msg, "UNIQUE constraint failed") || strings.Contains(msg, "SQLSTATE 23505") ||
		strings.Contains(msg, "duplicate key value")
}
