package routes

import (
	"net/http"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
)

// RegisterHealthRoutes exposes a minimal unauthenticated health endpoint.
func RegisterHealthRoutes(router *mux.Router, h handler.Handler) {
	router.HandleFunc("/health", health).Methods("GET")
	router.HandleFunc("/healthz", health).Methods("GET")
	router.HandleFunc("/status", h.GetStatus).Methods("GET")
}

func health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok\n"))
}
