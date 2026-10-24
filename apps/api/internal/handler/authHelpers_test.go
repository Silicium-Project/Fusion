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
	first := "  Jean   Pierre "
	password := strings.Repeat("x", 60)
	user, err := registrationUser(RegisterRequest{Email: " User@Example.test ", Password: password, Username: &empty, FirstName: &first})
	if err != nil {
		t.Fatal(err)
	}
	if user.Email != "user@example.test" || user.Username != nil || *user.FirstName != "Jean Pierre" || !user.CheckPassword(password) || user.PasswordHash == password {
		t.Fatal("invalid normalized account or password")
	}
}

func TestRegistrationRejectsInvalidFields(t *testing.T) {
	text := func(value string) *string { return &value }
	for name, req := range map[string]RegisterRequest{
		"not an email":       {Email: "invalid", Password: "password"},
		"display name":       {Email: "Name <user@example.test>", Password: "password"},
		"no domain dot":      {Email: "user@localhost", Password: "password"},
		"quoted local part":  {Email: `"a b"@example.test`, Password: "password"},
		"too long email":     {Email: strings.Repeat("a", 65) + "@example.test", Password: "password"},
		"empty password":     {Email: "user@example.test", Password: ""},
		"short password":     {Email: "user@example.test", Password: "1234567"},
		"long password":      {Email: "user@example.test", Password: strings.Repeat("x", 73)},
		"long username":      {Email: "user@example.test", Password: "password", Username: text(strings.Repeat("x", 31))},
		"short username":     {Email: "user@example.test", Password: "password", Username: text("ab")},
		"username with @":    {Email: "user@example.test", Password: "password", Username: text("other@example.test")},
		"username spaces":    {Email: "user@example.test", Password: "password", Username: text("john doe")},
		"reserved username":  {Email: "user@example.test", Password: "password", Username: text("Admin")},
		"long first name":    {Email: "user@example.test", Password: "password", FirstName: text(strings.Repeat("é", 51))},
		"name with digits":   {Email: "user@example.test", Password: "password", LastName: text("R2D2")},
		"name with markup":   {Email: "user@example.test", Password: "password", LastName: text("<script>")},
		"name with zero-wid": {Email: "user@example.test", Password: "password", LastName: text("Bob\u200b")},
	} {
		if _, err := registrationUser(req); err == nil {
			t.Fatalf("%s: invalid registration accepted", name)
		}
	}
	for _, name := range []string{"Zoë", "Jean-Luc", "O’Neil", "D'Artagnan", "José María", "Björk", "Łukasz", "李"} {
		if _, err := registrationUser(RegisterRequest{Email: "user@example.test", Password: "password", LastName: text(name)}); err != nil {
			t.Fatalf("%q refused: %v", name, err)
		}
	}
}

func TestJobTitlesAndDescriptionsAreChecked(t *testing.T) {
	if title, key := validJobTitle("  Rendu   v4 ", "x"); key != "" || title != "Rendu v4" {
		t.Fatalf("title = %q, %q", title, key)
	}
	if title, _ := validJobTitle("", "Raytracer"); title != "Raytracer" {
		t.Fatalf("default title = %q", title)
	}
	for _, title := range []string{strings.Repeat("x", 121), "a\x00b", "invoice\u202Etxt.exe"} {
		if _, key := validJobTitle(title, ""); key == "" {
			t.Fatalf("title %q accepted", title)
		}
	}
	if _, key := validJobDescription("line 1\nline 2\twith tab"); key != "" {
		t.Fatal("multiline description refused")
	}
	if _, key := validJobDescription(strings.Repeat("x", 1001)); key == "" {
		t.Fatal("long description accepted")
	}
	if _, key := validJobPriority("critical", "high"); key == "" {
		t.Fatal("unknown priority accepted")
	}
}

func TestStoredFileNamesAreSafe(t *testing.T) {
	for in, want := range map[string]string{
		"scene.cfg":                       "scene.cfg",
		`C:\Users\me\My Scene.cfg`:        "My_Scene.cfg",
		"../../etc/passwd":                "passwd",
		"..":                              "input.bin",
		".hidden":                         "hidden",
		"rapport été.pdf":                 "rapport__t_.pdf",
		strings.Repeat("a", 300) + ".txt": strings.Repeat("a", 96) + ".txt",
	} {
		if got := safeFilename(in); got != want {
			t.Fatalf("safeFilename(%q) = %q, want %q", in, got, want)
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
		r := httptest.NewRequest("POST", "/register", nil)
		if authDatabaseOK(w, r, test.err, "account.taken") || w.Code != test.status || strings.Contains(w.Body.String(), "SQL") {
			t.Fatalf("unexpected error response: %d %s", w.Code, w.Body.String())
		}
	}
}
