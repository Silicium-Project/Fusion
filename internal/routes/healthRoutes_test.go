package routes

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
)

func TestRegisterHealthRoutes(t *testing.T) {
	router := mux.NewRouter()
	RegisterHealthRoutes(router, handler.New(nil))

	for _, path := range []string{"/health", "/healthz"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		rr := httptest.NewRecorder()

		router.ServeHTTP(rr, req)

		if rr.Code != http.StatusOK {
			t.Fatalf("%s: expected status %d, got %d", path, http.StatusOK, rr.Code)
		}
		if body := rr.Body.String(); body != "ok\n" {
			t.Fatalf("%s: expected body %q, got %q", path, "ok\n", body)
		}
	}
}
