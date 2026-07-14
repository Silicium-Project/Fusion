package models

import (
	"golang.org/x/crypto/bcrypt"
	"gorm.io/gorm"
	"time"
)

// User corresponds to the 'users' table in the database
type User struct {
	ID            uint      `gorm:"primaryKey" json:"id"`
	FirstName     *string   `json:"firstName,omitempty"`
	LastName      *string   `json:"lastName,omitempty"`
	Email         string    `gorm:"unique;not null" json:"email"`
	PasswordHash  string    `gorm:"not null" json:"-"` // Omit from JSON responses
	Username      *string   `gorm:"unique" json:"username,omitempty"`
	WalletAddress *string   `gorm:"unique" json:"walletAddress,omitempty"`
	Role          string    `gorm:"not null;default:'user'" json:"role"`
	CreatedAt     time.Time `json:"createdAt"`
	UpdatedAt     time.Time `json:"updatedAt"`
}

// BeforeSave is a GORM hook that runs before a user record is created or updated.
// It hashes the password if it has been changed.
func (u *User) BeforeSave(tx *gorm.DB) (err error) {
	if len(u.PasswordHash) > 0 {
		// bcrypt.Cost validates the complete encoded hash. Checking only its
		// length would store a 60-character plain-text password unchanged.
		if _, err := bcrypt.Cost([]byte(u.PasswordHash)); err == nil {
			return nil
		}
		hashedPassword, err := bcrypt.GenerateFromPassword([]byte(u.PasswordHash), bcrypt.DefaultCost)
		if err != nil {
			return err
		}
		u.PasswordHash = string(hashedPassword)
	}
	return nil
}

// CheckPassword compares a plain-text password with the stored hash.
func (u *User) CheckPassword(password string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(password))
	return err == nil
}
