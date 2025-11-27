package db

import (
	"os"

	"github.com/silicium/internal/utils"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func Init() *gorm.DB {
	dbURL := os.Getenv("DATABASE_URL")

	db, err := gorm.Open(postgres.Open(dbURL), &gorm.Config{})
	utils.LogFatal(err, "Failed to connect to database")

	err = db.AutoMigrate()
	utils.LogFatal(err, "Failed to migrate database")

	return db
}
