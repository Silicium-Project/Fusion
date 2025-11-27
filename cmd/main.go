package main

import (
	"log"
	"net/http"

	"github.com/gorilla/mux"
	"github.com/rs/cors"
	"github.com/silicium/internal/db"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/utils"
)

func main() {
	DB := db.Init()
	h := handler.New(DB)

	// CORS Setup
	c := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE"},
		AllowedHeaders:   []string{"Content-Type", "Origin", "Accept", "*"},
		AllowCredentials: true,
	})

	// Router creation
	router := mux.NewRouter()
	registerRoutes(router, h)
	han := c.Handler(router)

	// Listen & Serve
	log.Println("Listening on port 8080")
	err := http.ListenAndServe(":8080", han)
	utils.LogFatal(err, "Error starting server")

}

func registerRoutes(router *mux.Router, h handler.Handler) {
	// Will define later routes here
}
