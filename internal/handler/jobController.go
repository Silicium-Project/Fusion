// Job HTTP handlers: create, list, get and cancel a job, and the background
// run of a job on the Silicium network.

package handler

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

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
	if header.Size > maxJobInputBytes {
		http.Error(w, "Input file exceeds the 16 MiB limit", http.StatusRequestEntityTooLarge)
		return
	}

	jobID := silicium.NewJobID(userID)
	inputDir := filepath.Join(envDefault("SILICIUM_SITE_STORAGE_DIR", filepath.Join("storage", "jobs")), jobID, "input")
	inputPath, err := storeJobInput(inputDir, header.Filename, file)
	if err != nil {
		log.Printf("store job %q input in %q: %v", jobID, inputDir, err)
		status := http.StatusInternalServerError
		message := "Could not store input file"
		if errors.Is(err, errEmptyJobInput) {
			status = http.StatusBadRequest
			message = "Input file cannot be empty"
		} else if errors.Is(err, errJobInputTooLarge) {
			status = http.StatusRequestEntityTooLarge
			message = "Input file exceeds the 16 MiB limit"
		}
		http.Error(w, message, status)
		return
	}
	removeInputOnFailure := true
	defer func() {
		if removeInputOnFailure {
			_ = os.Remove(inputPath)
		}
	}()
	absoluteInput, err := filepath.Abs(inputPath)
	if err != nil {
		http.Error(w, "Could not resolve input file", http.StatusInternalServerError)
		return
	}

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
		DeadlineAt:    &deadline,
	}
	if result := h.DB.Create(&job); result.Error != nil {
		http.Error(w, "Could not create job: "+result.Error.Error(), http.StatusInternalServerError)
		return
	}
	removeInputOnFailure = false

	if h.jobRunner != nil {
		go h.jobRunner(job.ID)
	} else {
		go h.runSiliciumJob(job.ID)
	}

	writeJSON(w, http.StatusAccepted, job)
}

func (h *Handler) ListJobs(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}
	// Reconcile only network work already owned by this user before querying.
	// The shared registry is telemetry, not an authorization boundary.
	if err := h.syncNetworkJobs(uint(userID)); err != nil {
		log.Printf("network job sync: %v", err)
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
