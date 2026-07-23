package main

import (
	"context"
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
	"github.com/silicium/internal/utils"
)

func main() {
	DB := db.Init()
	h := handler.New(DB)
	go h.RunTerminalJobControlReconciler(context.Background(), 30*time.Second)

	// CORS Setup
	c := cors.New(cors.Options{
		AllowedOrigins:   strings.Split(envDefault("CORS_ALLOWED_ORIGINS", "*"), ","),
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE"},
		AllowedHeaders:   []string{"Authorization", "Content-Type", "Origin", "Accept", "*"},
		AllowCredentials: true,
	})

	// Router creation
	router := mux.NewRouter()
	routes.RegisterUserRoutes(router, h) // Register user routes
	routes.RegisterJobRoutes(router, h)
	han := c.Handler(router)

	// Listen & Serve
	log.Println("Listening on port 8080")
	host := envDefault("HOST", "0.0.0.0")
	port := envDefault("PORT", "8080")
	err := http.ListenAndServe(host+":"+port, han)
	utils.LogFatal(err, "Error starting server")

}

func envDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}
