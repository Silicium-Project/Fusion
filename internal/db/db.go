package db

import (
	"os"

	"github.com/silicium/internal/models" // Import the models package
	"github.com/silicium/internal/utils"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func Init() *gorm.DB {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		utils.LogFatal(os.ErrInvalid, "DATABASE_URL is required")
	}

	db, err := gorm.Open(postgres.Open(dbURL), &gorm.Config{})
	utils.LogFatal(err, "Failed to connect to database")

	err = db.AutoMigrate(&models.User{}, &models.Job{})
	utils.LogFatal(err, "Failed to migrate database")

	return db
}
