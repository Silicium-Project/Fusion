package handler

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/mail"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/golang-jwt/jwt/v5"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

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
	if identifier == "" {
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

func optionalText(value *string) *string {
	if value == nil || strings.TrimSpace(*value) == "" {
		return nil
	}
	trimmed := strings.TrimSpace(*value)
	return &trimmed
}

func registrationUser(req RegisterRequest) (*models.User, error) {
	email := normalizeEmail(req.Email)
	address, err := mail.ParseAddress(email)
	if err != nil || address.Address != email || len(email) > 254 {
		return nil, errors.New("Saisissez une adresse e-mail valide.")
	}
	user := &models.User{Email: email, Role: "user", Username: optionalText(req.Username),
		FirstName: optionalText(req.FirstName), LastName: optionalText(req.LastName)}
	for _, name := range []*string{user.Username, user.FirstName, user.LastName} {
		if name != nil && utf8.RuneCountInString(*name) > 50 {
			return nil, errors.New("Les noms sont limités à 50 caractères.")
		}
	}
	return user, user.SetPassword(req.Password)
}

func (h *Handler) emailAvailable(w http.ResponseWriter, r *http.Request, email string) bool {
	var count int64
	err := h.DB.WithContext(r.Context()).Model(&models.User{}).Where("LOWER(TRIM(email)) = ?", email).Count(&count).Error
	if !authDatabaseOK(w, err) {
		return false
	}
	if count != 0 {
		writeAuthJSON(w, 409, map[string]string{"message": "Cette adresse e-mail est déjà utilisée."})
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

func authDatabaseOK(w http.ResponseWriter, err error) bool {
	if err == nil {
		return true
	}
	var duplicate interface{ SQLState() string }
	if errors.Is(err, gorm.ErrDuplicatedKey) || (errors.As(err, &duplicate) && duplicate.SQLState() == "23505") {
		writeAuthJSON(w, 409, map[string]string{"message": "Cette adresse e-mail ou ce nom d'utilisateur est déjà utilisé."})
		return false
	}
	log.Printf("Authentication database request failed: %v", err)
	writeAuthJSON(w, 503, map[string]string{"message": "Le service est indisponible. Réessayez plus tard."})
	return false
}

// Keep the existing bearer-token response and lifetimes; no new session protocol.
func loginTokens(user models.User) (map[string]string, error) {
	claims := &JWTClaims{Role: user.Role, RegisteredClaims: loginClaims(user.ID, 15*time.Minute)}
	access, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(jwtKey)
	if err != nil {
		return nil, err
	}
	refreshClaims := loginClaims(user.ID, 7*24*time.Hour)
	refresh, err := jwt.NewWithClaims(jwt.SigningMethodHS256, &refreshClaims).SignedString(jwtKey)
	if err != nil {
		return nil, err
	}
	return map[string]string{"token": access, "refresh_token": refresh}, nil
}

func loginClaims(id uint, lifetime time.Duration) jwt.RegisteredClaims {
	return jwt.RegisteredClaims{
		Subject:   strconv.FormatUint(uint64(id), 10),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(lifetime)),
	}
}
