package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/silicium/internal/auth"
)

func TestJWTMiddlewareOnlyAcceptsAccessTokens(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) })
	handler := JwtMiddleware(next)
	access, _ := auth.IssueAccess(7, "user", time.Now())
	refresh, _ := auth.IssueRefresh(7, time.Now())
	expired, _ := auth.IssueAccess(7, "user", time.Now().Add(-time.Hour))
	for name, test := range map[string]struct {
		header string
		want   int
	}{
		"access token":  {"Bearer " + access, http.StatusNoContent},
		"refresh token": {"Bearer " + refresh, http.StatusUnauthorized},
		"expired token": {"Bearer " + expired, http.StatusUnauthorized},
		"no scheme":     {access, http.StatusUnauthorized},
		"empty":         {"", http.StatusUnauthorized},
	} {
		request := httptest.NewRequest(http.MethodGet, "/user", nil)
		request.Header.Set("Authorization", test.header)
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, request)
		if response.Code != test.want {
			t.Fatalf("%s: got %d, want %d", name, response.Code, test.want)
		}
	}
}
