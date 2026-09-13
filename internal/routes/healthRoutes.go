package routes

import (
	"encoding/json"
	"net/http"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/release"
)

// RegisterHealthRoutes exposes a minimal unauthenticated health endpoint.
func RegisterHealthRoutes(router *mux.Router, h handler.Handler) {
	router.HandleFunc("/health", health).Methods("GET")
	router.HandleFunc("/healthz", health).Methods("GET")
	router.HandleFunc("/version", version).Methods("GET")
	router.HandleFunc("/status", h.GetStatus).Methods("GET")
}

func health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok\n"))
}

func version(w http.ResponseWriter, r *http.Request) {
	metadata := release.Current()
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(map[string]string{
		"service":        "backend",
		"version":        metadata.Version,
		"release_channel": metadata.Channel,
		"release_build":   metadata.Build,
	})
}
