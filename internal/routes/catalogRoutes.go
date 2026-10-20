package routes

import (
	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
)

// RegisterCatalogRoutes exposes the AI catalogue (public, read only).
func RegisterCatalogRoutes(router *mux.Router, h handler.Handler) {
	catalogRouter := router.PathPrefix("/catalog").Subrouter()
	catalogRouter.HandleFunc("/tasks", h.ListCatalogTasks).Methods("GET")
	catalogRouter.HandleFunc("/models", h.ListCatalogModels).Methods("GET")
	catalogRouter.HandleFunc("/models/{key}", h.GetCatalogModel).Methods("GET")
	catalogRouter.HandleFunc("/models/{key}/quote", h.GetCatalogQuote).Methods("GET")
}
