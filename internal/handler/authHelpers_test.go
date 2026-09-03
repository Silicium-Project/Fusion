package handler

import (
	"errors"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestLoginIdentifierSupportsNewAndExistingClients(t *testing.T) {
	for _, test := range []struct {
		req  LoginRequest
		want string
	}{
		{LoginRequest{Identifier: " TestUser "}, "TestUser"},
		{LoginRequest{Identifier: " USER@EXAMPLE.TEST "}, "USER@EXAMPLE.TEST"},
		{LoginRequest{Email: " legacy@example.test "}, "legacy@example.test"},
		{LoginRequest{Identifier: "current", Email: "legacy@example.test"}, "current"},
		{LoginRequest{Identifier: "  "}, ""},
	} {
		if got := loginIdentifier(test.req); got != test.want {
			t.Fatalf("identifier = %q, want %q", got, test.want)
		}
	}
}

func TestRegistrationNormalizesFieldsAndHashesPassword(t *testing.T) {
	empty := "  "
	password := strings.Repeat("x", 60)
	user, err := registrationUser(RegisterRequest{Email: " User@Example.test ", Password: password, Username: &empty})
	if err != nil {
		t.Fatal(err)
	}
	if user.Email != "user@example.test" || user.Username != nil || !user.CheckPassword(password) || user.PasswordHash == password {
		t.Fatal("invalid normalized account or password")
	}
}

func TestRegistrationRejectsInvalidFields(t *testing.T) {
	longName := strings.Repeat("x", 51)
	for _, req := range []RegisterRequest{
		{Email: "invalid", Password: "password"},
		{Email: "Name <user@example.test>", Password: "password"},
		{Email: "user@example.test", Password: ""},
		{Email: "user@example.test", Password: strings.Repeat("x", 73)},
		{Email: "user@example.test", Password: "password", Username: &longName},
	} {
		if _, err := registrationUser(req); err == nil {
			t.Fatal("invalid registration accepted")
		}
	}
}

type duplicateAccountError struct{}

func (duplicateAccountError) Error() string    { return "private SQL details" }
func (duplicateAccountError) SQLState() string { return "23505" }

func TestAuthDatabaseErrorsAreActionableAndPrivate(t *testing.T) {
	for _, test := range []struct {
		err    error
		status int
	}{
		{duplicateAccountError{}, 409}, {errors.New("private SQL details"), 503},
	} {
		w := httptest.NewRecorder()
		if authDatabaseOK(w, test.err) || w.Code != test.status || strings.Contains(w.Body.String(), "SQL") {
			t.Fatalf("unexpected error response: %d %s", w.Code, w.Body.String())
		}
	}
}
