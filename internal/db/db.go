package db

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/glebarez/sqlite"
	"github.com/silicium/internal/catalog"
	"github.com/silicium/internal/models" // Import the models package
	"github.com/silicium/internal/utils"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func databaseDialector() (gorm.Dialector, error) {
	driver := strings.ToLower(strings.TrimSpace(os.Getenv("DATABASE_DRIVER")))
	databaseURL := strings.TrimSpace(os.Getenv("DATABASE_URL"))
	if driver == "" {
		if databaseURL != "" {
			driver = "postgres"
		} else {
			driver = "sqlite"
		}
	}

	switch driver {
	case "sqlite":
		path := strings.TrimSpace(os.Getenv("SQLITE_PATH"))
		if path == "" {
			path = filepath.Join(".silicium", "site", "silicium.db")
		}
		if path != ":memory:" {
			if err := os.MkdirAll(filepath.Dir(path), 0o750); err != nil {
				return nil, fmt.Errorf("create sqlite directory: %w", err)
			}
		}
		return sqlite.Open(path), nil
	case "postgres", "postgresql":
		if databaseURL == "" {
			return nil, errors.New("DATABASE_URL is required when DATABASE_DRIVER=postgres")
		}
		return postgres.Open(databaseURL), nil
	default:
		return nil, fmt.Errorf("unsupported DATABASE_DRIVER %q", driver)
	}
}

func Init() *gorm.DB {
	dialector, err := databaseDialector()
	utils.LogFatal(err, "Failed to configure database")

	db, err := gorm.Open(dialector, &gorm.Config{})
	utils.LogFatal(err, "Failed to connect to database")

	err = db.AutoMigrate(&models.User{}, &models.Job{})
	utils.LogFatal(err, "Failed to migrate database")

	err = catalog.Migrate(db)
	utils.LogFatal(err, "Failed to migrate the AI catalog")

	return db
}
