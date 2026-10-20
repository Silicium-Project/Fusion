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
	router.HandleFunc("/refresh", h.RefreshToken).Methods("POST")

	// Create a subrouter for routes that require authentication
	authRouter := router.PathPrefix("/user").Subrouter()
	authRouter.Use(middleware.JwtMiddleware)

	// Protected routes
	authRouter.HandleFunc("", h.GetUser).Methods("GET")
	authRouter.HandleFunc("", h.UpdateUser).Methods("PUT", "PATCH")
	authRouter.HandleFunc("", h.DeleteUser).Methods("DELETE")
	authRouter.HandleFunc("/password", h.ChangePassword).Methods("PUT")
	authRouter.HandleFunc("/wallet/challenge", h.IssueWalletChallenge).Methods("POST")
	authRouter.HandleFunc("/wallet", h.ConnectWallet).Methods("POST")
	authRouter.HandleFunc("/devices", h.ListUserDevices).Methods("GET")
	authRouter.HandleFunc("/devices/pairing-code", h.CreateDevicePairingCode).Methods("POST")
	authRouter.HandleFunc("/devices/{id}", h.UnlinkUserDevice).Methods("DELETE")

	// The desktop node completes a short-lived pairing with a signature from
	// its persistent P2P identity. Possessing the one-time code authorizes the
	// account selected in the web interface.
	router.HandleFunc("/devices/pair", h.PairDevice).Methods("POST")
}
