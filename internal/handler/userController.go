package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/silicium/internal/contextkeys" // Import the shared context keys package
	"github.com/silicium/internal/models"
)

var jwtKey []byte

func init() {
	// Initialize jwtKey from environment variable
	key := os.Getenv("JWT_SECRET_KEY")
	if key == "" {
		// Fallback to a default or log a fatal error in production
		fmt.Println("WARNING: JWT_SECRET_KEY environment variable not set. Using a default key. DO NOT USE IN PRODUCTION.")
		key = "supersecretdevelopmentkeythatshouldneverbeusedinproduction"
	}
	jwtKey = []byte(key)
}

// JWTClaims includes the user role along with registered claims
type JWTClaims struct {
	Role string `json:"role"`
	jwt.RegisteredClaims
}

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

func (h *Handler) Register(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, 400, map[string]string{"message": "Le formulaire est invalide."})
		return
	}
	user, err := registrationUser(req)
	if err != nil {
		writeAuthJSON(w, 400, map[string]string{"message": err.Error()})
		return
	}
	if !h.emailAvailable(w, r, user.Email) {
		return
	}
	if !authDatabaseOK(w, h.DB.WithContext(r.Context()).Create(user).Error) {
		return
	}
	writeAuthJSON(w, http.StatusCreated, map[string]string{"message": "Compte créé. Vous pouvez vous connecter."})
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, 400, map[string]string{"message": "Le formulaire est invalide."})
		return
	}
	users, err := loginUsers(h.DB.WithContext(r.Context()), loginIdentifier(req))
	if !authDatabaseOK(w, err) {
		return
	}
	if len(users) != 1 || !users[0].CheckPassword(req.Password) {
		writeAuthJSON(w, 401, map[string]string{"message": "Identifiant ou mot de passe incorrect."})
		return
	}
	tokens, err := loginTokens(users[0])
	if err != nil {
		writeAuthJSON(w, 500, map[string]string{"message": "La connexion est momentanément indisponible."})
		return
	}
	writeAuthJSON(w, http.StatusOK, tokens)
}

type RefreshRequest struct {
	RefreshToken string `json:"refresh_token"`
}

func (h *Handler) RefreshToken(w http.ResponseWriter, r *http.Request) {
	var req RefreshRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La demande de renouvellement est invalide."})
		return
	}

	claims := &jwt.RegisteredClaims{}
	token, err := jwt.ParseWithClaims(req.RefreshToken, claims, func(token *jwt.Token) (interface{}, error) {
		return jwtKey, nil
	}, jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}), jwt.WithExpirationRequired())

	if err != nil || !token.Valid {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session a expiré. Reconnectez-vous."})
		return
	}

	userID := claims.Subject
	var user models.User
	if result := h.DB.WithContext(r.Context()).First(&user, userID); result.Error != nil {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est plus valide."})
		return
	}

	expirationTime := time.Now().Add(15 * time.Minute)
	newClaims := &JWTClaims{
		Role: user.Role,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			ExpiresAt: jwt.NewNumericDate(expirationTime),
		},
	}

	newToken := jwt.NewWithClaims(jwt.SigningMethodHS256, newClaims)
	newTokenString, err := newToken.SignedString(jwtKey)
	if err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "La session ne peut pas être renouvelée."})
		return
	}

	writeAuthJSON(w, http.StatusOK, map[string]string{
		"token": newTokenString,
	})
}

func (h *Handler) GetUser(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}

	var user models.User
	if result := h.DB.First(&user, userIDStr); result.Error != nil {
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(user)
}

func (h *Handler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}

	var req UpdateUserRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	var user models.User
	if result := h.DB.First(&user, userIDStr); result.Error != nil {
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	if req.Username != nil {
		user.Username = req.Username
	}
	if req.FirstName != nil {
		user.FirstName = req.FirstName
	}
	if req.LastName != nil {
		user.LastName = req.LastName
	}

	if result := h.DB.Save(&user); result.Error != nil {
		http.Error(w, "Could not update user", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(user)
}

type ChangePasswordRequest struct {
	CurrentPassword string `json:"currentPassword"`
	NewPassword     string `json:"newPassword"`
}

func (h *Handler) ChangePassword(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}

	var req ChangePasswordRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.NewPassword == "" || req.CurrentPassword == "" {
		http.Error(w, "Both current and new password are required", http.StatusBadRequest)
		return
	}

	var user models.User
	if result := h.DB.First(&user, userIDStr); result.Error != nil {
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	if !user.CheckPassword(req.CurrentPassword) {
		http.Error(w, "Invalid current password", http.StatusUnauthorized)
		return
	}

	if err := user.SetPassword(req.NewPassword); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if result := h.DB.Save(&user); result.Error != nil {
		http.Error(w, "Could not update password", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"message": "Password updated successfully"})
}

func (h *Handler) DeleteUser(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}

	if result := h.DB.Delete(&models.User{}, userIDStr); result.Error != nil {
		http.Error(w, "Could not delete user", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"message": "User deleted successfully"})
}

func (h *Handler) IssueWalletChallenge(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	userID, err := strconv.ParseUint(userIDStr, 10, 64)
	if err != nil || userID == 0 || h.walletChallenges == nil {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	var req WalletChallengeRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La demande de portefeuille est invalide."})
		return
	}
	if _, err := validateWalletAddress(req.WalletAddress); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’adresse Solana n’est pas valide."})
		return
	}
	challenge, err := h.walletChallenges.issue(uint(userID), req.WalletAddress, time.Now())
	if err != nil {
		writeAuthJSON(w, http.StatusInternalServerError, map[string]string{"message": "Le challenge ne peut pas être créé."})
		return
	}
	writeAuthJSON(w, http.StatusOK, map[string]string{
		"challenge": challenge.Nonce,
		"message":   challenge.Message,
		"expiresAt": challenge.ExpiresAt.Format(time.RFC3339),
	})
}

func (h *Handler) ConnectWallet(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}
	userID, err := strconv.ParseUint(userIDStr, 10, 64)
	if err != nil || userID == 0 || h.walletChallenges == nil {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La session n’est pas valide."})
		return
	}

	var req ConnectWalletRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 24<<10)).Decode(&req); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "La preuve du portefeuille est invalide."})
		return
	}

	if _, err := validateWalletAddress(req.WalletAddress); err != nil {
		writeAuthJSON(w, http.StatusBadRequest, map[string]string{"message": "L’adresse Solana n’est pas valide."})
		return
	}
	challenge, err := h.walletChallenges.consume(uint(userID), req.WalletAddress, req.Challenge, time.Now())
	if err != nil {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "Le challenge a expiré ou a déjà été utilisé."})
		return
	}
	if err := verifyWalletSignature(req.WalletAddress, challenge.Message, req.Signature); err != nil {
		writeAuthJSON(w, http.StatusUnauthorized, map[string]string{"message": "La signature Phantom n’est pas valide."})
		return
	}

	var user models.User
	if result := h.DB.WithContext(r.Context()).First(&user, userIDStr); result.Error != nil {
		writeAuthJSON(w, http.StatusNotFound, map[string]string{"message": "Le compte n’existe plus."})
		return
	}

	user.WalletAddress = &req.WalletAddress

	if result := h.DB.WithContext(r.Context()).Save(&user); !authDatabaseOK(w, result.Error) {
		return
	}

	writeAuthJSON(w, http.StatusOK, map[string]string{"message": "Portefeuille vérifié et connecté."})
}
