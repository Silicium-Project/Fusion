package handler

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

func (h *Handler) CreateJob(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}
	if err := r.ParseMultipartForm(16 << 20); err != nil {
		http.Error(w, "Invalid multipart form", http.StatusBadRequest)
		return
	}

	workload := strings.TrimSpace(r.FormValue("workload"))
	if workload == "" {
		workload = "raytracer"
	}
	if err := silicium.ValidateWorkload(workload); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	file, header, err := r.FormFile("file")
	if err != nil {
		http.Error(w, "Input file is required", http.StatusBadRequest)
		return
	}
	defer file.Close()

	jobID := silicium.NewJobID(userID)
	inputDir := filepath.Join(envDefault("SILICIUM_SITE_STORAGE_DIR", filepath.Join("storage", "jobs")), jobID, "input")
	if err := os.MkdirAll(inputDir, 0o755); err != nil {
		http.Error(w, "Could not create job input directory", http.StatusInternalServerError)
		return
	}
	inputPath := filepath.Join(inputDir, safeFilename(header.Filename))
	target, err := os.Create(inputPath)
	if err != nil {
		http.Error(w, "Could not store input file", http.StatusInternalServerError)
		return
	}
	defer target.Close()
	if _, err := io.Copy(target, file); err != nil {
		http.Error(w, "Could not write input file", http.StatusInternalServerError)
		return
	}
	absoluteInput, _ := filepath.Abs(inputPath)

	job := models.Job{
		UserID:        userID,
		Title:         envDefaultValue(r.FormValue("title"), "Raytracer"),
		Description:   strings.TrimSpace(r.FormValue("description")),
		Workload:      workload,
		Priority:      envDefaultValue(r.FormValue("priority"), "high"),
		Status:        "queued",
		SiliciumJobID: jobID,
		InputPath:     absoluteInput,
		DashboardURL:  silicium.ConfigFromEnv().DashboardURL,
	}
	if result := h.DB.Create(&job); result.Error != nil {
		http.Error(w, "Could not create job: "+result.Error.Error(), http.StatusInternalServerError)
		return
	}

	go h.runSiliciumJob(job.ID)

	writeJSON(w, http.StatusAccepted, job)
}

func (h *Handler) ListJobs(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}
	var jobs []models.Job
	if result := h.DB.Where("user_id = ?", userID).Order("created_at desc").Find(&jobs); result.Error != nil {
		http.Error(w, "Could not list jobs", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusOK, jobs)
}

func (h *Handler) GetJob(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, job)
}

func (h *Handler) GetJobDashboard(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}

	summary := readJSONMap(job.SummaryPath)
	if len(summary) == 0 {
		summary = readJSONMap(progressPathForJob(job))
	}
	trace := readJSONMap(job.DevnetTracePath)
	devnetTrace, _ := summary["devnet_trace"].(map[string]any)
	if len(trace) == 0 {
		if inner, ok := devnetTrace["trace"].(map[string]any); ok {
			trace = inner
		}
	}

	payload := map[string]any{
		"job": map[string]any{
			"id":            job.ID,
			"title":         job.Title,
			"description":   job.Description,
			"workload":      job.Workload,
			"priority":      job.Priority,
			"status":        job.Status,
			"siliciumJobId": job.SiliciumJobID,
			"devnetJob":     job.DevnetJob,
			"dashboardUrl":  job.DashboardURL,
			"errorMessage":  job.ErrorMessage,
			"createdAt":     job.CreatedAt,
			"startedAt":     job.StartedAt,
			"completedAt":   job.CompletedAt,
		},
		"resultReady": job.ResultPath != "",
		"resultUrl":   "/jobs/" + strconv.Itoa(int(job.ID)) + "/result",
		"diagnostics": map[string]any{
			"inputPath":       job.InputPath,
			"resultPath":      job.ResultPath,
			"summaryPath":     job.SummaryPath,
			"progressPath":    progressPathForJob(job),
			"devnetTracePath": job.DevnetTracePath,
		},
		"summary": map[string]any{
			"success":          summary["success"],
			"progress":         summary["progress"],
			"stage":            summary["stage"],
			"updatedUtc":       summary["updated_utc"],
			"demoMode":         summary["demo_mode"],
			"jobId":            summary["job_id"],
			"fragmentCount":    summary["fragment_count"],
			"finalHash":        summary["final_hash"],
			"reassembledHash":  summary["reassembled_hash"],
			"expectedFullHash": summary["expected_full_hash"],
			"image":            summary["image"],
			"network":          summary["network"],
			"fragments":        summary["fragments"],
			"nodeRuns":         summary["node_runs"],
			"splitTree":        summary["split_tree"],
		},
		"devnet": map[string]any{
			"enabled":    devnetTrace["enabled"],
			"ok":         devnetTrace["ok"],
			"status":     devnetTrace["status"],
			"job":        trace["job"],
			"programId":  trace["program_id"],
			"rpc":        trace["rpc"],
			"signatures": trace["signatures"],
			"fragments":  trace["fragments"],
			"splitTree":  trace["split_tree"],
		},
	}
	writeJSON(w, http.StatusOK, payload)
}

func (h *Handler) GetJobResult(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if job.ResultPath == "" {
		http.Error(w, "Result is not ready", http.StatusNotFound)
		return
	}
	http.ServeFile(w, r, job.ResultPath)
}

func (h *Handler) GetJobFragmentPreview(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if strings.TrimSpace(job.Workload) != "raytracer" {
		http.Error(w, "Fragment previews are only available for raytracer jobs", http.StatusNotFound)
		return
	}
	index, err := strconv.Atoi(mux.Vars(r)["index"])
	if err != nil || index < 0 || index > 9999 {
		http.Error(w, "Invalid fragment index", http.StatusBadRequest)
		return
	}

	previewPath := filepath.Join(filepath.Dir(progressPathForJob(job)), "fragments", fmt.Sprintf("fragment-%03d.png", index))
	info, err := os.Stat(previewPath)
	if err != nil || !info.Mode().IsRegular() {
		http.Error(w, "Fragment preview is not ready", http.StatusNotFound)
		return
	}

	w.Header().Set("Cache-Control", "private, max-age=3600, immutable")
	w.Header().Set("Content-Type", "image/png")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	http.ServeFile(w, r, previewPath)
}

func (h *Handler) runSiliciumJob(jobID uint) {
	var job models.Job
	if result := h.DB.First(&job, jobID); result.Error != nil {
		return
	}
	now := time.Now()
	h.DB.Model(&job).Updates(map[string]any{"status": "running", "started_at": &now})

	runResult := silicium.RunJob(job, silicium.ConfigFromEnv())
	updates := map[string]any{
		"status":            runResult.Status,
		"result_path":       runResult.ResultPath,
		"summary_path":      runResult.SummaryPath,
		"devnet_trace_path": runResult.DevnetTracePath,
		"devnet_job":        runResult.DevnetJob,
		"error_message":     runResult.ErrorMessage,
		"dashboard_url":     silicium.ConfigFromEnv().DashboardURL,
		"completed_at":      time.Now(),
	}
	h.DB.Model(&models.Job{}).Where("id = ?", jobID).Updates(updates)
}

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

func readJSONMap(path string) map[string]any {
	if strings.TrimSpace(path) == "" {
		return map[string]any{}
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return map[string]any{}
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return map[string]any{}
	}
	return payload
}

func progressPathForJob(job models.Job) string {
	networkRoot := envDefault("SILICIUM_NETWORK_ROOT", filepath.Clean(filepath.Join("..", "..", "Network")))
	if strings.TrimSpace(job.Workload) == "raytracer" {
		if strings.TrimSpace(job.SummaryPath) != "" {
			return filepath.Join(filepath.Dir(job.SummaryPath), "raytracer-progress.json")
		}
		return filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "raytracer-progress.json")
	}
	if strings.TrimSpace(job.SummaryPath) != "" {
		return filepath.Join(filepath.Dir(job.SummaryPath), "auto-split-demo-progress.json")
	}
	return filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "raytracer-progress.json")
}

func safeFilename(name string) string {
	base := filepath.Base(name)
	base = strings.ReplaceAll(base, " ", "_")
	if base == "." || base == string(filepath.Separator) || base == "" {
		return "input.json"
	}
	return base
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
