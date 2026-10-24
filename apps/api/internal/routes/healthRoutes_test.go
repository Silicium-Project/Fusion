package routes

import (
	"encoding/json"
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

func TestVersionReportsReleaseChannel(t *testing.T) {
	t.Setenv("SILICIUM_RELEASE_CHANNEL", "dev")
	t.Setenv("SILICIUM_RELEASE_VERSION", "0.2.9-dev.29")
	t.Setenv("SILICIUM_RELEASE_BUILD", "build-dev")

	router := mux.NewRouter()
	RegisterHealthRoutes(router, handler.New(nil))
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, httptest.NewRequest(http.MethodGet, "/version", nil))

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status %d, got %d", http.StatusOK, rr.Code)
	}
	var payload map[string]string
	if err := json.Unmarshal(rr.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["service"] != "backend" || payload["release_channel"] != "dev" || payload["version"] != "0.2.9-dev.29" || payload["release_build"] != "build-dev" {
		t.Fatalf("unexpected version payload: %#v", payload)
	}
}
