package routes

import (
	"github.com/gorilla/mux"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/middleware"
)

// RegisterUserRoutes sets up the user-related routes.
func RegisterUserRoutes(router *mux.Router, h handler.Handler) {
	// Public routes for registration and login
	router.HandleFunc("/register", h.Register).Methods("POST")
	router.HandleFunc("/login", h.Login).Methods("POST")

	// Create a subrouter for routes that require authentication
	authRouter := router.PathPrefix("/user").Subrouter()
	authRouter.Use(middleware.JwtMiddleware)

	// Protected routes
	authRouter.HandleFunc("", h.GetUser).Methods("GET")
	authRouter.HandleFunc("", h.UpdateUser).Methods("PUT", "PATCH")
	authRouter.HandleFunc("", h.DeleteUser).Methods("DELETE")
	authRouter.HandleFunc("/password", h.ChangePassword).Methods("PUT")
	authRouter.HandleFunc("/wallet", h.ConnectWallet).Methods("POST")
}
