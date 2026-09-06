package middleware

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestJWTMiddlewareRequiresHS256AndExpiry(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusNoContent) })
	handler := JwtMiddleware(next)
	for _, test := range []struct {
		name   string
		method jwt.SigningMethod
		expiry *jwt.NumericDate
		want   int
	}{
		{"valid", jwt.SigningMethodHS256, jwt.NewNumericDate(time.Now().Add(time.Minute)), http.StatusNoContent},
		{"wrong algorithm", jwt.SigningMethodHS384, jwt.NewNumericDate(time.Now().Add(time.Minute)), http.StatusUnauthorized},
		{"missing expiry", jwt.SigningMethodHS256, nil, http.StatusUnauthorized},
	} {
		t.Run(test.name, func(t *testing.T) {
			token := jwt.NewWithClaims(test.method, jwt.RegisteredClaims{Subject: "7", ExpiresAt: test.expiry})
			signed, err := token.SignedString(jwtKey)
			if err != nil {
				t.Fatal(err)
			}
			request := httptest.NewRequest(http.MethodGet, "/user", nil)
			request.Header.Set("Authorization", "Bearer "+signed)
			response := httptest.NewRecorder()
			handler.ServeHTTP(response, request)
			if response.Code != test.want {
				t.Fatalf("got %d, want %d", response.Code, test.want)
			}
		})
	}
}
