package db

import (
	"path/filepath"
	"testing"
)

func TestDatabaseDialectorDefaultsToLocalSQLite(t *testing.T) {
	t.Setenv("DATABASE_DRIVER", "")
	t.Setenv("DATABASE_URL", "")
	t.Setenv("SQLITE_PATH", filepath.Join(t.TempDir(), "site", "silicium.db"))

	dialector, err := databaseDialector()
	if err != nil {
		t.Fatal(err)
	}
	if got := dialector.Name(); got != "sqlite" {
		t.Fatalf("default database driver = %q, want sqlite", got)
	}
}

func TestDatabaseDialectorRequiresPostgresURL(t *testing.T) {
	t.Setenv("DATABASE_DRIVER", "postgres")
	t.Setenv("DATABASE_URL", "")

	if _, err := databaseDialector(); err == nil {
		t.Fatal("expected a missing PostgreSQL URL to fail configuration")
	}
}
