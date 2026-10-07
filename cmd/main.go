package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/gorilla/mux"
	"github.com/rs/cors"
	"github.com/silicium/internal/auth"
	"github.com/silicium/internal/db"
	"github.com/silicium/internal/handler"
	"github.com/silicium/internal/middleware"
	"github.com/silicium/internal/release"
	"github.com/silicium/internal/routes"
)

func main() {
	if err := release.Validate(os.Getenv("SILICIUM_RELEASE_CHANNEL")); err != nil {
		log.Fatal(err)
	}
	if err := auth.CheckKey(os.Getenv("SILICIUM_RELEASE_CHANNEL")); err != nil {
		log.Fatal(err)
	}
	applicationContext, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	database := db.Init()
	h := handler.New(database)
	go h.RunTerminalJobControlReconciler(applicationContext, 30*time.Second)

	router := mux.NewRouter()
	router.UseEncodedPath()
	router.PathPrefix("/docs/").Handler(http.StripPrefix("/docs/", http.FileServer(http.Dir("./docs/"))))
	routes.RegisterHealthRoutes(router, h)
	routes.RegisterUserRoutes(router, h)
	routes.RegisterJobRoutes(router, h)

	origins := splitValues(envDefault("CORS_ALLOWED_ORIGINS", "*"))
	allowCredentials := true
	for _, origin := range origins {
		if origin == "*" {
			allowCredentials = false
			break
		}
	}
	corsHandler := cors.New(cors.Options{
		AllowedOrigins:   origins,
		AllowedMethods:   []string{http.MethodGet, http.MethodPost, http.MethodPut, http.MethodPatch, http.MethodDelete, http.MethodOptions},
		AllowedHeaders:   []string{"Authorization", "Content-Type", "Origin", "Accept", "Accept-Language", "X-Request-ID"},
		ExposedHeaders:   []string{"X-Request-ID", "X-Total-Count", "X-Page", "X-Page-Size", "X-Silicium-Cache"},
		AllowCredentials: allowCredentials,
		MaxAge:           600,
	}).Handler(router)

	httpHandler := middleware.Recover(middleware.RequestID(middleware.SecurityHeaders(corsHandler)))
	host := envDefault("HOST", "0.0.0.0")
	port := envDefault("PORT", "8080")
	server := &http.Server{
		Addr:              host + ":" + port,
		Handler:           httpHandler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       45 * time.Second,
		WriteTimeout:      5 * time.Minute,
		IdleTimeout:       60 * time.Second,
	}

	serverErrors := make(chan error, 1)
	go func() {
		log.Printf("Silicium API listening on %s", server.Addr)
		serverErrors <- server.ListenAndServe()
	}()

	select {
	case <-applicationContext.Done():
		log.Printf("Silicium API shutdown requested")
	case err := <-serverErrors:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("Silicium API stopped unexpectedly: %v", err)
		}
		return
	}

	shutdownContext, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownContext); err != nil {
		log.Printf("Silicium API graceful shutdown failed: %v", err)
		_ = server.Close()
	}
}

func envDefault(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func splitValues(value string) []string {
	parts := strings.Split(value, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		if trimmed := strings.TrimSpace(part); trimmed != "" {
			values = append(values, trimmed)
		}
	}
	if len(values) == 0 {
		return []string{"*"}
	}
	return values
}
