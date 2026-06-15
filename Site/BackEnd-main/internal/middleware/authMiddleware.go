package middleware

import (
	"context"
	"fmt"
	"github.com/golang-jwt/jwt/v5"
	"github.com/silicium/internal/contextkeys" // Import the shared context keys package
	"net/http"
	"os"
	"strings"
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

func JwtMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Authorization header required", http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		if tokenString == authHeader { // No "Bearer " prefix
			http.Error(w, "Invalid token format", http.StatusUnauthorized)
			return
		}

		claims := &jwt.RegisteredClaims{}

		token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
			return jwtKey, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		// The subject of the token is the user ID.
		userID := claims.Subject
		if userID == "" {
			http.Error(w, "Invalid token: user ID not found", http.StatusUnauthorized)
			return
		}

		// Store the user ID in the request context for later handlers to use.
		ctx := context.WithValue(r.Context(), contextkeys.UserIDKey, userID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
