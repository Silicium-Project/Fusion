package models

import (
	"errors"
	"time"

	"golang.org/x/crypto/bcrypt"
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

// SetPassword hashes plaintext explicitly, even when its length is 60 bytes.
// Call only when setting a password, never when saving an unchanged profile.
func (u *User) SetPassword(password string) error {
	if len(password) == 0 || len(password) > 72 {
		return errors.New("Le mot de passe doit contenir entre 1 et 72 octets.")
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err == nil {
		u.PasswordHash = string(hash)
	}
	return err
}

// CheckPassword compares a plain-text password with the stored hash.
func (u *User) CheckPassword(password string) bool {
	err := bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(password))
	return err == nil
}
