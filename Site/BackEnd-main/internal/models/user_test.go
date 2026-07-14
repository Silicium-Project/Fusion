package models

import (
	"strings"
	"testing"

	"golang.org/x/crypto/bcrypt"
)

func TestBeforeSaveHashesSixtyCharacterPlaintext(t *testing.T) {
	plain := strings.Repeat("p", 60)
	user := User{PasswordHash: plain}

	if err := user.BeforeSave(nil); err != nil {
		t.Fatalf("BeforeSave returned an error: %v", err)
	}
	if user.PasswordHash == plain {
		t.Fatal("60-character plaintext password was stored unchanged")
	}
	if err := bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(plain)); err != nil {
		t.Fatalf("stored password is not a valid hash of the plaintext: %v", err)
	}
}

func TestBeforeSaveKeepsExistingBcryptHash(t *testing.T) {
	hash, err := bcrypt.GenerateFromPassword([]byte("correct horse battery staple"), bcrypt.MinCost)
	if err != nil {
		t.Fatal(err)
	}
	user := User{PasswordHash: string(hash)}

	if err := user.BeforeSave(nil); err != nil {
		t.Fatalf("BeforeSave returned an error: %v", err)
	}
	if user.PasswordHash != string(hash) {
		t.Fatal("existing bcrypt hash was unexpectedly changed")
	}
}
