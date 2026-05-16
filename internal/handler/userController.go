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
	Email    string `json:"email"`
	Password string `json:"password"`
}

type ConnectWalletRequest struct {
	WalletAddress string `json:"walletAddress"`
}

type UpdateUserRequest struct {
	Username  *string `json:"username,omitempty"`
	FirstName *string `json:"firstName,omitempty"`
	LastName  *string `json:"lastName,omitempty"`
}

func (h *Handler) Register(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Basic validation
	if req.Email == "" || req.Password == "" {
		http.Error(w, "Email and password are required", http.StatusBadRequest)
		return
	}

	user := models.User{
		Email:        req.Email,
		PasswordHash: req.Password, // The hook in user.go will hash this
		Username:     req.Username,
		FirstName:    req.FirstName,
		LastName:     req.LastName,
		Role:         "user", // Default role
	}

	// The BeforeSave hook will hash the password
	if result := h.DB.Create(&user); result.Error != nil {
		http.Error(w, "Could not create user: "+result.Error.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]string{"message": "User created successfully"})
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	var user models.User
	if result := h.DB.Where("email = ?", req.Email).First(&user); result.Error != nil {
		http.Error(w, "Invalid email or password", http.StatusUnauthorized)
		return
	}

	if !user.CheckPassword(req.Password) {
		http.Error(w, "Invalid email or password", http.StatusUnauthorized)
		return
	}

	expirationTime := time.Now().Add(24 * time.Hour)
	claims := &JWTClaims{
		Role: user.Role,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   strconv.FormatUint(uint64(user.ID), 10),
			ExpiresAt: jwt.NewNumericDate(expirationTime),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString(jwtKey)
	if err != nil {
		http.Error(w, "Could not generate token", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"token": tokenString})
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

	// The BeforeSave hook will hash the new password
	user.PasswordHash = req.NewPassword
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

func (h *Handler) ConnectWallet(w http.ResponseWriter, r *http.Request) {
	userIDStr, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}

	var req ConnectWalletRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.WalletAddress == "" {
		http.Error(w, "Wallet address is required", http.StatusBadRequest)
		return
	}

	var user models.User
	if result := h.DB.First(&user, userIDStr); result.Error != nil {
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	user.WalletAddress = &req.WalletAddress

	if result := h.DB.Save(&user); result.Error != nil {
		http.Error(w, "Could not connect wallet", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"message": "Wallet connected successfully"})
}
