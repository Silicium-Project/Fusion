package main

import (
	"log"
	"net/http"

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

	// CORS Setup
	c := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
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
	err := http.ListenAndServe(":8080", han)
	utils.LogFatal(err, "Error starting server")

}
