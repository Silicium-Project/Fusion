package middleware

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/silicium/internal/auth"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/i18n"
)

// JwtMiddleware lets through the requests carrying a valid access token
// (`Authorization: Bearer …`) and puts the user id in their context.
// Refresh tokens are refused here: they only renew a session.
func JwtMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		parts := strings.Fields(r.Header.Get("Authorization"))
		if len(parts) != 2 || !strings.EqualFold(parts[0], "Bearer") || parts[1] == "" {
			writeUnauthorized(w, i18n.R(r, "session.bearer_required"))
			return
		}
		userID, err := auth.ParseAccess(parts[1])
		if err != nil {
			writeUnauthorized(w, i18n.R(r, "session.expired"))
			return
		}
		ctx := context.WithValue(r.Context(), contextkeys.UserIDKey, userID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func writeUnauthorized(w http.ResponseWriter, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusUnauthorized)
	_ = json.NewEncoder(w).Encode(map[string]string{"message": message})
}
