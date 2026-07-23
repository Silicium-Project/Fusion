package handler

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
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
	fragmentCount := 0
	if raw := strings.TrimSpace(r.FormValue("fragment_count")); raw != "" {
		parsed, parseErr := strconv.Atoi(raw)
		if parseErr != nil || parsed < 1 || parsed > 256 {
			http.Error(w, "fragment_count must be between 1 and 256", http.StatusBadRequest)
			return
		}
		fragmentCount = parsed
	}
	maxRuntimeSeconds := 3600
	if raw := strings.TrimSpace(r.FormValue("max_runtime_seconds")); raw != "" {
		parsed, parseErr := strconv.Atoi(raw)
		if parseErr != nil || parsed < 30 || parsed > 86400 {
			http.Error(w, "max_runtime_seconds must be between 30 and 86400", http.StatusBadRequest)
			return
		}
		maxRuntimeSeconds = parsed
	}
	deadline := time.Now().Add(time.Duration(maxRuntimeSeconds) * time.Second)

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
		FragmentCount: fragmentCount,
		Status:        "queued",
		SiliciumJobID: jobID,
		InputPath:     absoluteInput,
		DashboardURL:  silicium.ConfigFromEnv().DashboardURL,
		DeadlineAt:    &deadline,
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
	page := boundedQueryInt(r, "page", 1, 1, 1_000_000)
	pageSize := boundedQueryInt(r, "page_size", 20, 1, 100)
	query := h.DB.Model(&models.Job{}).Where("user_id = ?", userID)
	if status := strings.TrimSpace(r.URL.Query().Get("status")); status != "" && status != "all" {
		query = query.Where("status = ?", status)
	}
	var total int64
	if result := query.Count(&total); result.Error != nil {
		http.Error(w, "Could not count jobs", http.StatusInternalServerError)
		return
	}
	var jobs []models.Job
	if result := query.Order("created_at desc").Offset((page - 1) * pageSize).Limit(pageSize).Find(&jobs); result.Error != nil {
		http.Error(w, "Could not list jobs", http.StatusInternalServerError)
		return
	}
	w.Header().Set("X-Total-Count", strconv.FormatInt(total, 10))
	w.Header().Set("X-Page", strconv.Itoa(page))
	w.Header().Set("X-Page-Size", strconv.Itoa(pageSize))
	w.Header().Set("Access-Control-Expose-Headers", "X-Total-Count, X-Page, X-Page-Size")
	writeJSON(w, http.StatusOK, jobs)
}

type cancelJobRequest struct {
	Reason string `json:"reason"`
}

func (h *Handler) CancelJob(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	if job.Status == "completed" || job.Status == "failed" || job.Status == "cancelled" || job.Status == "expired" {
		writeJSON(w, http.StatusOK, job)
		return
	}
	var request cancelJobRequest
	_ = json.NewDecoder(io.LimitReader(r.Body, 16<<10)).Decode(&request)
	reason := strings.TrimSpace(request.Reason)
	if reason == "" {
		reason = "cancelled by payer"
	}
	now := time.Now()
	updates := map[string]any{
		"status":              "cancelling",
		"cancel_requested_at": &now,
		"cancel_reason":       reason,
	}
	if result := h.DB.Model(&job).Updates(updates); result.Error != nil {
		http.Error(w, "Could not cancel job", http.StatusInternalServerError)
		return
	}
	control := silicium.TaskControl{
		ControlID:  fmt.Sprintf("%s-cancel-%d", job.SiliciumJobID, now.UnixNano()),
		RootJobID:  job.SiliciumJobID,
		Action:     "cancel",
		Reason:     reason,
		IssuerNode: silicium.ConfigFromEnv().OrchestratorNodeID,
		IssuedUTC:  now.UTC().Format(time.RFC3339Nano),
	}
	signalCtx, cancel := context.WithTimeout(r.Context(), 6*time.Second)
	signalErr := silicium.PublishTaskControl(signalCtx, silicium.ConfigFromEnv(), control)
	cancel()
	h.cancelRun(job.ID, errors.New(reason))
	billableUnits, receiptSetHash := verifiedBillingForJob(job)
	if signalErr != nil {
		h.DB.Model(&job).Update("error_message", "network cancellation announcement pending: "+signalErr.Error())
	}
	h.DB.Model(&job).Updates(map[string]any{
		"status":               "cancelled",
		"cancelled_at":         &now,
		"completed_at":         &now,
		"billable_work_units":  billableUnits,
		"compute_receipt_hash": receiptSetHash,
	})
	h.DB.First(&job, job.ID)
	writeJSON(w, http.StatusAccepted, job)
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
			"id":                 job.ID,
			"title":              job.Title,
			"description":        job.Description,
			"workload":           job.Workload,
			"priority":           job.Priority,
			"status":             job.Status,
			"siliciumJobId":      job.SiliciumJobID,
			"devnetJob":          job.DevnetJob,
			"dashboardUrl":       job.DashboardURL,
			"errorMessage":       job.ErrorMessage,
			"createdAt":          job.CreatedAt,
			"startedAt":          job.StartedAt,
			"completedAt":        job.CompletedAt,
			"deadlineAt":         job.DeadlineAt,
			"cancelledAt":        job.CancelledAt,
			"cancelReason":       job.CancelReason,
			"billableWorkUnits":  job.BillableWorkUnits,
			"computeReceiptHash": job.ComputeReceiptHash,
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
	if job.Status == "cancelled" || job.Status == "cancelling" {
		return
	}
	now := time.Now()
	h.DB.Model(&job).Updates(map[string]any{"status": "running", "started_at": &now})

	baseCtx, cancel := context.WithCancelCause(context.Background())
	ctx := context.Context(baseCtx)
	deadlineCancel := func() {}
	if job.DeadlineAt != nil {
		ctx, deadlineCancel = context.WithDeadlineCause(baseCtx, *job.DeadlineAt, errors.New("job deadline exceeded"))
	}
	h.registerRun(job.ID, cancel)
	defer h.unregisterRun(job.ID)
	defer cancel(nil)
	defer deadlineCancel()
	runResult := silicium.RunJob(ctx, job, silicium.ConfigFromEnv())
	var current models.Job
	h.DB.First(&current, jobID)
	if current.Status == "cancelled" || current.Status == "cancelling" {
		return
	}
	if errors.Is(context.Cause(ctx), context.DeadlineExceeded) || (job.DeadlineAt != nil && time.Now().After(*job.DeadlineAt)) {
		runResult.Status = "expired"
		runResult.ErrorMessage = "job deadline exceeded"
	}
	completedAt := time.Now()
	updates := map[string]any{
		"status":               runResult.Status,
		"result_path":          runResult.ResultPath,
		"summary_path":         runResult.SummaryPath,
		"devnet_trace_path":    runResult.DevnetTracePath,
		"devnet_job":           runResult.DevnetJob,
		"error_message":        runResult.ErrorMessage,
		"dashboard_url":        silicium.ConfigFromEnv().DashboardURL,
		"billable_work_units":  runResult.BillableWorkUnits,
		"compute_receipt_hash": runResult.ComputeReceiptHash,
		"completed_at":         completedAt,
	}
	h.DB.Model(&models.Job{}).Where("id = ?", jobID).Updates(updates)
	if runResult.Status == "failed" || runResult.Status == "expired" {
		signalCtx, signalCancel := context.WithTimeout(context.Background(), 12*time.Second)
		if err := publishTerminalTaskControl(signalCtx, job, runResult.Status, runResult.ErrorMessage); err != nil {
			h.DB.Model(&models.Job{}).Where("id = ?", jobID).
				Update("error_message", runResult.ErrorMessage+"\nnetwork terminal announcement pending: "+err.Error())
		}
		signalCancel()
	}
}

func boundedQueryInt(r *http.Request, key string, fallback, minimum, maximum int) int {
	value, err := strconv.Atoi(strings.TrimSpace(r.URL.Query().Get(key)))
	if err != nil {
		return fallback
	}
	if value < minimum {
		return minimum
	}
	if value > maximum {
		return maximum
	}
	return value
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

func verifiedBillingForJob(job models.Job) (uint64, string) {
	payload := readJSONMap(job.SummaryPath)
	if len(payload) == 0 {
		payload = readJSONMap(progressPathForJob(job))
	}
	if billing, ok := payload["billing"].(map[string]any); ok {
		units, _ := billing["billable_work_units"].(float64)
		receiptHash, _ := billing["receipt_set_hash"].(string)
		return uint64(max(0, units)), receiptHash
	}
	fragments, _ := payload["fragments"].([]any)
	var units uint64
	receiptHashes := make([]string, 0, len(fragments)*2)
	for _, raw := range fragments {
		fragment, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		attestation, ok := fragment["receipt_attestation"].(map[string]any)
		if !ok || attestation["accepted"] != true {
			continue
		}
		for _, key := range []string{"compute_billable_work_units", "verify_billable_work_units"} {
			if value, ok := fragment[key].(float64); ok && value > 0 {
				units += uint64(value)
			}
		}
		for _, key := range []string{"compute_receipt_hash", "verify_receipt_hash"} {
			if value, ok := fragment[key].(string); ok && value != "" {
				receiptHashes = append(receiptHashes, value)
			}
		}
	}
	if len(receiptHashes) == 0 {
		return units, ""
	}
	digest := sha256.Sum256([]byte(strings.Join(receiptHashes, "\n")))
	return units, fmt.Sprintf("%x", digest)
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
