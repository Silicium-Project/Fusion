// Account handlers: registration, login, session renewal, profile,
// password, deletion and the Phantom wallet link. Every message is in the
// language of the request (`Accept-Language`).

package handler

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/silicium/internal/auth"
	"github.com/silicium/internal/models"
)

type RegisterRequest struct {
	Email     string  `json:"email"`
	Password  string  `json:"password"`
	Username  *string `json:"username,omitempty"`
	FirstName *string `json:"first_name,omitempty"`
	LastName  *string `json:"last_name,omitempty"`
}

type LoginRequest struct {
	Identifier string `json:"identifier"`
	Email      string `json:"email"` // Kept for existing API clients.
	Password   string `json:"password"`
}

type ConnectWalletRequest struct {
	WalletAddress string `json:"walletAddress"`
	Challenge     string `json:"challenge"`
	Signature     string `json:"signature"`
}

type WalletChallengeRequest struct {
	WalletAddress string `json:"walletAddress"`
}

type UpdateUserRequest struct {
	Username  *string `json:"username,omitempty"`
	FirstName *string `json:"firstName,omitempty"`
	LastName  *string `json:"lastName,omitempty"`
}

type RefreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

type ChangePasswordRequest struct {
	CurrentPassword string `json:"currentPassword"`
	NewPassword     string `json:"newPassword"`
}

func (h *Handler) Register(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	user, err := registrationUser(req)
	if err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": errorMessage(r, err)})
		return
	}
	if !h.emailAvailable(w, r, user.Email) || !h.usernameAvailable(w, r, user.Username, 0) {
		return
	}
	if !authDatabaseOK(w, r, h.DB.WithContext(r.Context()).Create(user).Error, "account.taken") {
		return
	}
	writeAuthMessage(w, r, http.StatusCreated, "account.created")
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	identifier := loginIdentifier(req)
	now := time.Now()
	if wait := h.logins.blockedFor(identifier, now); wait > 0 {
		minutes := int(wait/time.Minute) + 1
		w.Header().Set("Retry-After", strconv.Itoa(int(wait.Seconds())+1))
		writeAuthMessage(w, r, http.StatusTooManyRequests, "login.too_many", minutes)
		return
	}
	users, err := loginUsers(h.DB.WithContext(r.Context()), identifier)
	if !authDatabaseOK(w, r, err, "account.taken") {
		return
	}
	if len(users) != 1 || !users[0].CheckPassword(req.Password) {
		h.logins.fail(identifier, now)
		writeAuthMessage(w, r, http.StatusUnauthorized, "login.invalid")
		return
	}
	h.logins.succeed(identifier)
	tokens, err := loginTokens(users[0])
	if err != nil {
		writeAuthMessage(w, r, http.StatusInternalServerError, "login.unavailable")
		return
	}
	writeAuthJSON(w, http.StatusOK, tokens)
}

// RefreshToken answers POST /refresh: a new access token for a valid
// refresh token of an account that still exists.
func (h *Handler) RefreshToken(w http.ResponseWriter, r *http.Request) {
	var req RefreshRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	userID, err := auth.ParseRefresh(req.RefreshToken)
	if err != nil {
		writeAuthMessage(w, r, http.StatusUnauthorized, "session.expired")
		return
	}
	var user models.User
	if result := h.DB.WithContext(r.Context()).First(&user, "id = ?", userID); result.Error != nil {
		writeAuthMessage(w, r, http.StatusUnauthorized, "session.invalid")
		return
	}
	token, err := auth.IssueAccess(user.ID, user.Role, time.Now())
	if err != nil {
		writeAuthMessage(w, r, http.StatusInternalServerError, "session.renew_failed")
		return
	}
	writeAuthJSON(w, http.StatusOK, map[string]string{"token": token})
}

// currentUser loads the account of the request; false (after answering)
// when it no longer exists.
func (h *Handler) currentUser(w http.ResponseWriter, r *http.Request) (models.User, bool) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		writeAuthMessage(w, r, http.StatusUnauthorized, "session.invalid")
		return models.User{}, false
	}
	var user models.User
	if result := h.DB.WithContext(r.Context()).First(&user, "id = ?", userID); result.Error != nil {
		writeAuthMessage(w, r, http.StatusNotFound, "account.not_found")
		return models.User{}, false
	}
	return user, true
}

func (h *Handler) GetUser(w http.ResponseWriter, r *http.Request) {
	if user, ok := h.currentUser(w, r); ok {
		writeAuthJSON(w, http.StatusOK, user)
	}
}

// UpdateUser answers PATCH /user: the fields sent are checked and saved; an
// empty field clears it.
func (h *Handler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	var req UpdateUserRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}
	if req.Username != nil {
		username, key := validUsername(req.Username)
		if key != "" {
			writeAuthMessage(w, r, http.StatusBadRequest, key)
			return
		}
		if !h.usernameAvailable(w, r, username, user.ID) {
			return
		}
		user.Username = username
	}
	for _, field := range []struct {
		value  *string
		target **string
	}{{req.FirstName, &user.FirstName}, {req.LastName, &user.LastName}} {
		if field.value == nil {
			continue
		}
		name, key := validPersonName(field.value)
		if key != "" {
			writeAuthMessage(w, r, http.StatusBadRequest, key)
			return
		}
		*field.target = name
	}
	if !authDatabaseOK(w, r, h.DB.WithContext(r.Context()).Save(&user).Error, "username.taken") {
		return
	}
	writeAuthJSON(w, http.StatusOK, user)
}

// usernameAvailable checks that no other account uses `username`, ignoring
// case ("Thom" and "thom" would be mistaken for one another).
func (h *Handler) usernameAvailable(w http.ResponseWriter, r *http.Request, username *string, self uint) bool {
	if username == nil {
		return true
	}
	var count int64
	err := h.DB.WithContext(r.Context()).Model(&models.User{}).
		Where("LOWER(username) = ? AND id <> ?", strings.ToLower(*username), self).Count(&count).Error
	if !authDatabaseOK(w, r, err, "username.taken") {
		return false
	}
	if count != 0 {
		writeAuthMessage(w, r, http.StatusConflict, "username.taken")
		return false
	}
	return true
}

// ChangePassword answers PUT /user/password. A wrong current password is a
// 400, not a 401: the session itself is valid and must not be ended.
func (h *Handler) ChangePassword(w http.ResponseWriter, r *http.Request) {
	var req ChangePasswordRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	if req.NewPassword == "" || req.CurrentPassword == "" {
		writeAuthMessage(w, r, http.StatusBadRequest, "password.required")
		return
	}
	if key, args := validNewPassword(req.NewPassword); key != "" {
		writeAuthMessage(w, r, http.StatusBadRequest, key, args...)
		return
	}
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}
	if !user.CheckPassword(req.CurrentPassword) {
		writeAuthMessage(w, r, http.StatusBadRequest, "password.current_wrong")
		return
	}
	if err := user.SetPassword(req.NewPassword); err != nil {
		writeAuthMessage(w, r, http.StatusBadRequest, "password.too_long")
		return
	}
	if !authDatabaseOK(w, r, h.DB.WithContext(r.Context()).Save(&user).Error, "account.taken") {
		return
	}
	writeAuthMessage(w, r, http.StatusOK, "password.updated")
}

func (h *Handler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}
	if result := h.DB.WithContext(r.Context()).Delete(&models.User{}, user.ID); result.Error != nil {
		writeAuthMessage(w, r, http.StatusInternalServerError, "account.delete_failed")
		return
	}
	writeAuthMessage(w, r, http.StatusOK, "account.deleted")
}

func (h *Handler) IssueWalletChallenge(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok || h.walletChallenges == nil {
		writeAuthMessage(w, r, http.StatusUnauthorized, "session.invalid")
		return
	}
	var req WalletChallengeRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	if _, err := validateWalletAddress(req.WalletAddress); err != nil {
		writeAuthMessage(w, r, http.StatusBadRequest, "wallet.address_invalid")
		return
	}
	challenge, err := h.walletChallenges.issue(userID, req.WalletAddress, time.Now())
	if err != nil {
		writeAuthMessage(w, r, http.StatusInternalServerError, "wallet.challenge_failed")
		return
	}
	writeAuthJSON(w, http.StatusOK, map[string]string{
		"challenge": challenge.Nonce,
		"message":   challenge.Message,
		"expiresAt": challenge.ExpiresAt.Format(time.RFC3339),
	})
}

func (h *Handler) ConnectWallet(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok || h.walletChallenges == nil {
		writeAuthMessage(w, r, http.StatusUnauthorized, "session.invalid")
		return
	}
	var req ConnectWalletRequest
	if !decodeAuthBody(w, r, &req) {
		return
	}
	if _, err := validateWalletAddress(req.WalletAddress); err != nil {
		writeAuthMessage(w, r, http.StatusBadRequest, "wallet.address_invalid")
		return
	}
	challenge, err := h.walletChallenges.consume(userID, req.WalletAddress, req.Challenge, time.Now())
	if err != nil {
		writeAuthMessage(w, r, http.StatusBadRequest, "wallet.challenge_expired")
		return
	}
	if err := verifyWalletSignature(req.WalletAddress, challenge.Message, req.Signature); err != nil {
		writeAuthMessage(w, r, http.StatusBadRequest, "wallet.signature_invalid")
		return
	}
	user, ok := h.currentUser(w, r)
	if !ok {
		return
	}
	address := strings.TrimSpace(req.WalletAddress)
	user.WalletAddress = &address
	if !authDatabaseOK(w, r, h.DB.WithContext(r.Context()).Save(&user).Error, "wallet.taken") {
		return
	}
	writeAuthMessage(w, r, http.StatusOK, "wallet.connected")
}
