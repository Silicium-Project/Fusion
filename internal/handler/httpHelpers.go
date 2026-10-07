// Small request/response and environment helpers shared by the handlers.

package handler

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"strings"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/i18n"
	"github.com/silicium/internal/models"
)

func (h *Handler) jobForRequest(w http.ResponseWriter, r *http.Request) (models.Job, bool) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return models.Job{}, false
	}
	id, err := strconv.Atoi(mux.Vars(r)["id"])
	if err != nil || id <= 0 {
		http.Error(w, "Invalid job id", http.StatusBadRequest)
		return models.Job{}, false
	}
	var job models.Job
	if result := h.DB.Where("id = ? AND user_id = ?", id, userID).First(&job); result.Error != nil {
		http.Error(w, "Job not found", http.StatusNotFound)
		return models.Job{}, false
	}
	return job, true
}

func userIDFromRequest(r *http.Request) (uint, bool) {
	raw, ok := r.Context().Value(contextkeys.UserIDKey).(string)
	if !ok {
		return 0, false
	}
	id, err := strconv.ParseUint(raw, 10, 64)
	if err != nil || id == 0 {
		return 0, false
	}
	return uint(id), true
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func envDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func envDefaultValue(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}

// writeMessage answers `{"message": …}`, the message in the language of the
// request.
func writeMessage(w http.ResponseWriter, r *http.Request, status int, key string, args ...any) {
	writeJSON(w, status, map[string]string{"message": i18n.R(r, key, args...)})
}
