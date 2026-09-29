// Job dashboard, result download and fragment preview endpoints.

package handler

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/gorilla/mux"
)

func (h *Handler) GetJobDashboard(w http.ResponseWriter, r *http.Request) {
	job, ok := h.jobForRequest(w, r)
	if !ok {
		return
	}
	job = h.refreshRaytracerArtifacts(job)

	summary := readJSONMap(job.SummaryPath)
	if len(summary) == 0 {
		summary = readJSONMap(progressPathForJob(job))
	}
	if strings.HasPrefix(job.InputPath, "rpc://") {
		summary = h.networkJobSummary(job.SiliciumJobID, summary)
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
			"network":            job.NetworkMetadata,
		},
		"resultReady": regularFile(job.ResultPath),
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
			"error":            summary["error"],
			"errorType":        summary["error_type"],
			"traceback":        summary["traceback"],
			"failureDetail":    summary["failure_detail"],
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
			"performance":      summary["performance"],
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
	job = h.refreshRaytracerArtifacts(job)
	if !regularFile(job.ResultPath) {
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
	job = h.refreshRaytracerArtifacts(job)
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
