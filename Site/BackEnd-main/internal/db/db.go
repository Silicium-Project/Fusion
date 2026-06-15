package db

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/glebarez/sqlite"
	"github.com/silicium/internal/models" // Import the models package
	"github.com/silicium/internal/utils"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func Init() *gorm.DB {
	dbURL := os.Getenv("DATABASE_URL")
	driver := strings.ToLower(strings.TrimSpace(os.Getenv("DATABASE_DRIVER")))
	if driver == "" {
		if dbURL != "" {
			driver = "postgres"
		} else {
			driver = "sqlite"
		}
	}

	var dialector gorm.Dialector
	switch driver {
	case "postgres", "postgresql":
		dialector = postgres.Open(dbURL)
	case "sqlite", "sqlite3":
		sqlitePath := os.Getenv("SQLITE_PATH")
		if sqlitePath == "" {
			sqlitePath = filepath.Join("storage", "silicium.db")
		}
		if err := os.MkdirAll(filepath.Dir(sqlitePath), 0755); err != nil {
			utils.LogFatal(err, "Failed to create sqlite directory")
		}
		dialector = sqlite.Open(sqlitePath)
	default:
		utils.LogFatal(fmt.Errorf("unsupported database driver %q", driver), "Failed to configure database")
	}

	db, err := gorm.Open(dialector, &gorm.Config{})
	utils.LogFatal(err, "Failed to connect to database")

	err = db.AutoMigrate(&models.User{}, &models.Job{})
	utils.LogFatal(err, "Failed to migrate database")

	return db
}
