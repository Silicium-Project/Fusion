package middleware

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
	"github.com/silicium/internal/contextkeys"
)

var jwtKey []byte

func init() {
	key := os.Getenv("JWT_SECRET_KEY")
	if key == "" {
		fmt.Println("WARNING: JWT_SECRET_KEY environment variable not set. Using a development-only key.")
		key = "supersecretdevelopmentkeythatshouldneverbeusedinproduction"
	}
	jwtKey = []byte(key)
}

func JwtMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parts := strings.Fields(r.Header.Get("Authorization"))
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || parts[1] == "" {
			writeUnauthorized(w, "Une authentification Bearer est requise.")
			return
		}

		claims := &jwt.RegisteredClaims{}
		token, err := jwt.ParseWithClaims(parts[1], claims, func(token *jwt.Token) (interface{}, error) {
			return jwtKey, nil
		}, jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}), jwt.WithExpirationRequired())
		if err != nil || !token.Valid || strings.TrimSpace(claims.Subject) == "" {
			writeUnauthorized(w, "La session est invalide ou expirée.")
			return
		}

		ctx := context.WithValue(r.Context(), contextkeys.UserIDKey, claims.Subject)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func writeUnauthorized(w http.ResponseWriter, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]string{"message": message})
}
