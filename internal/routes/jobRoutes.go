package routes

import (
	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/middleware"
)

func RegisterJobRoutes(router *mux.Router, h handler.Handler) {
	jobsRouter := router.PathPrefix("/jobs").Subrouter()
	jobsRouter.Use(middleware.JwtMiddleware)

	jobsRouter.HandleFunc("", h.CreateJob).Methods("POST")
	jobsRouter.HandleFunc("", h.ListJobs).Methods("GET")
	jobsRouter.HandleFunc("/network/peers", h.GetNetworkPeers).Methods("GET")
	jobsRouter.HandleFunc("/{id}", h.GetJob).Methods("GET")
	jobsRouter.HandleFunc("/{id}/cancel", h.CancelJob).Methods("POST")
	jobsRouter.HandleFunc("/{id}/dashboard", h.GetJobDashboard).Methods("GET")
	jobsRouter.HandleFunc("/{id}/result", h.GetJobResult).Methods("GET")
	jobsRouter.HandleFunc("/{id}/fragments/{index}/preview", h.GetJobFragmentPreview).Methods("GET")
}
