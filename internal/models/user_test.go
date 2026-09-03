package models

import (
	"strings"
	"testing"
)

func TestSetPasswordAlwaysHashes(t *testing.T) {
	for _, password := range []string{"short", "correct-password", strings.Repeat("x", 60), strings.Repeat("x", 72)} {
		user := User{}
		if err := user.SetPassword(password); err != nil {
			t.Fatal(err)
		}
		if user.PasswordHash == password || !user.CheckPassword(password) || user.CheckPassword("wrong") {
			t.Fatal("password was not hashed and verified correctly")
		}
	}
}

func TestSetPasswordRejectsInvalidByteLengths(t *testing.T) {
	for _, password := range []string{"", strings.Repeat("x", 73), strings.Repeat("é", 37)} {
		user := User{PasswordHash: "unchanged"}
		if user.SetPassword(password) == nil || user.PasswordHash != "unchanged" {
			t.Fatal("invalid password accepted or existing hash changed")
		}
	}
}
