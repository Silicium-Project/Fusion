// Helpers of the account handlers: login lookup, registration checks, JSON
// answers and session tokens.

package handler

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/silicium/internal/auth"
	"github.com/silicium/internal/i18n"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

// maxAuthBodyBytes bounds the JSON body of the account requests.
const maxAuthBodyBytes = 16 << 10

func normalizeEmail(value string) string { return strings.ToLower(strings.TrimSpace(value)) }

func loginIdentifier(req LoginRequest) string {
	if identifier := strings.TrimSpace(req.Identifier); identifier != "" {
		return identifier
	}
	return strings.TrimSpace(req.Email)
}

// Email takes priority so a username cannot shadow another account's email.
// Username comparison keeps the database's existing case-sensitive uniqueness.
func loginUsers(db *gorm.DB, identifier string) ([]models.User, error) {
	if identifier == "" || len(identifier) > maxEmailLength {
		return nil, nil
	}
	var users []models.User
	err := db.Where("LOWER(TRIM(email)) = ?", normalizeEmail(identifier)).Limit(2).Find(&users).Error
	if err != nil || len(users) != 0 {
		return users, err
	}
	err = db.Where("username = ?", identifier).Limit(2).Find(&users).Error
	return users, err
}

// fieldError is a refusal of a form field: the i18n key and its arguments.
type fieldError struct {
	key  string
	args []any
}

func (e *fieldError) Error() string { return e.key }

func refuse(key string, args ...any) error { return &fieldError{key: key, args: args} }

// errorMessage is the message of `err` in the language of the request.
func errorMessage(r *http.Request, err error) string {
	var field *fieldError
	if errors.As(err, &field) {
		return i18n.R(r, field.key, field.args...)
	}
	return i18n.R(r, "form.invalid")
}

// registrationUser checks a registration and returns the account to create.
func registrationUser(req RegisterRequest) (*models.User, error) {
	email, key := validEmail(req.Email)
	if key != "" {
		return nil, refuse(key)
	}
	username, key := validUsername(req.Username)
	if key != "" {
		return nil, refuse(key)
	}
	firstName, key := validPersonName(req.FirstName)
	if key != "" {
		return nil, refuse(key)
	}
	lastName, key := validPersonName(req.LastName)
	if key != "" {
		return nil, refuse(key)
	}
	if key, args := validNewPassword(req.Password); key != "" {
		return nil, refuse(key, args...)
	}
	user := &models.User{Email: email, Role: "user", Username: username, FirstName: firstName, LastName: lastName}
	if err := user.SetPassword(req.Password); err != nil {
		return nil, refuse("password.too_long")
	}
	return user, nil
}

func (h *Handler) emailAvailable(w http.ResponseWriter, r *http.Request, email string) bool {
	var count int64
	err := h.DB.WithContext(r.Context()).Model(&models.User{}).Where("LOWER(TRIM(email)) = ?", email).Count(&count).Error
	if !authDatabaseOK(w, r, err, "account.taken") {
		return false
	}
	if count != 0 {
		writeAuthJSON(w, http.StatusConflict, map[string]string{"message": i18n.R(r, "email.taken")})
		return false
	}
	return true
}

func writeAuthJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

// writeAuthMessage answers `{"message": …}` in the language of the request.
func writeAuthMessage(w http.ResponseWriter, r *http.Request, status int, key string, args ...any) {
	writeAuthJSON(w, status, map[string]string{"message": i18n.R(r, key, args...)})
}

// authDatabaseOK answers the errors of an account query: a uniqueness
// conflict becomes a 409 with `takenKey`, anything else a 503 without the
// database details.
func authDatabaseOK(w http.ResponseWriter, r *http.Request, err error, takenKey string) bool {
	if err == nil {
		return true
	}
	var duplicate interface{ SQLState() string }
	if errors.Is(err, gorm.ErrDuplicatedKey) || (errors.As(err, &duplicate) && duplicate.SQLState() == "23505") ||
		strings.Contains(strings.ToLower(err.Error()), "unique constraint") {
		writeAuthMessage(w, r, http.StatusConflict, takenKey)
		return false
	}
	log.Printf("Authentication database request failed: %v", err)
	writeAuthMessage(w, r, http.StatusServiceUnavailable, "service.unavailable")
	return false
}

// loginTokens are the access and refresh tokens of a new session.
func loginTokens(user models.User) (map[string]string, error) {
	now := time.Now()
	access, err := auth.IssueAccess(user.ID, user.Role, now)
	if err != nil {
		return nil, err
	}
	refresh, err := auth.IssueRefresh(user.ID, now)
	if err != nil {
		return nil, err
	}
	return map[string]string{"token": access, "refresh_token": refresh}, nil
}

// decodeAuthBody reads a bounded JSON body into `target`, refusing unknown
// trailing data.
func decodeAuthBody(w http.ResponseWriter, r *http.Request, target any) bool {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxAuthBodyBytes))
	if err := decoder.Decode(target); err != nil || decoder.More() {
		writeAuthMessage(w, r, http.StatusBadRequest, "form.invalid")
		return false
	}
	return true
}
