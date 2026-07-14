package main

import (
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/rs/cors"
	"github.com/silicium/internal/db"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/routes" // Import the routes package
	"github.com/silicium/internal/security"
	"github.com/silicium/internal/utils"
)

func main() {
	if _, err := security.JWTKey(); err != nil {
		log.Fatal(err)
	}
	DB := db.Init()
	h := handler.New(DB)

	// CORS Setup
	allowedOrigins := strings.Split(envDefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"), ",")
	for i, origin := range allowedOrigins {
		allowedOrigins[i] = strings.TrimSpace(origin)
	}
	c := cors.New(cors.Options{
		AllowedOrigins:   allowedOrigins,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE"},
		AllowedHeaders:   []string{"Authorization", "Content-Type", "Origin", "Accept"},
		AllowCredentials: false,
	})

	// Router creation
	router := mux.NewRouter()
	router.HandleFunc("/health", healthHandler).Methods("GET")
	router.HandleFunc("/healthz", healthHandler).Methods("GET")
	routes.RegisterUserRoutes(router, h) // Register user routes
	routes.RegisterJobRoutes(router, h)
	han := c.Handler(router)

	// Listen & Serve
	host := envDefault("HOST", "0.0.0.0")
	port := envDefault("PORT", "8080")
	addr := host + ":" + port
	log.Println("Listening on", addr)
	server := &http.Server{
		Addr:              addr,
		Handler:           han,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       2 * time.Minute,
		WriteTimeout:      2 * time.Minute,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}
	err := server.ListenAndServe()
	utils.LogFatal(err, "Error starting server")

}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"ok":true}`))
}

func envDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}
