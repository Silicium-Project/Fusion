package middleware

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHTTPMiddlewareAddsRequestAndSecurityHeaders(t *testing.T) {
	handler := RequestID(SecurityHeaders(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNoContent)
	})))
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Header().Get("X-Request-ID") == "" || response.Header().Get("X-Content-Type-Options") != "nosniff" || response.Header().Get("X-Frame-Options") != "DENY" {
		t.Fatalf("missing hardening headers: %#v", response.Header())
	}
}

func TestRecoverReturnsPrivateJSONError(t *testing.T) {
	handler := Recover(http.HandlerFunc(func(http.ResponseWriter, *http.Request) { panic("private details") }))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest(http.MethodGet, "/panic", nil))
	if response.Code != http.StatusInternalServerError || !strings.Contains(response.Body.String(), "inattendue") || strings.Contains(response.Body.String(), "private details") {
		t.Fatalf("unexpected recovery response: %d %s", response.Code, response.Body.String())
	}
}
