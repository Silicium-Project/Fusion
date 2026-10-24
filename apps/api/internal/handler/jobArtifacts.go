// Raytracer job files on disk: job directories, safe artifact paths, progress
// file, verified billing, and refresh of the artifact fields of a job.

package handler

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

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

func regularFile(path string) bool {
	if strings.TrimSpace(path) == "" {
		return false
	}
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func raytracerJobDirectories(job models.Job) []string {
	cfg := silicium.ConfigFromEnv()
	storageRoot := strings.TrimSpace(cfg.WorkloadStorageDir)
	if storageRoot == "" {
		storageRoot = filepath.Join(cfg.NetworkRoot, ".silicium", "jobs")
	} else if !filepath.IsAbs(storageRoot) {
		storageRoot = filepath.Join(cfg.NetworkRoot, storageRoot)
	}
	if absolute, err := filepath.Abs(storageRoot); err == nil {
		storageRoot = absolute
	}

	candidates := make([]string, 0, 4)
	if strings.TrimSpace(job.SummaryPath) != "" {
		candidates = append(candidates, filepath.Dir(job.SummaryPath))
	}
	storageDir, ok := silicium.JobStorageDir(job.Workload)
	if !ok {
		storageDir = "raytracer"
	}
	candidates = append(candidates,
		filepath.Join(storageRoot, storageDir, job.SiliciumJobID),
		// Compatibility with the release that passed the generic workload
		// root directly to run_network_job.py.
		filepath.Join(storageRoot, job.SiliciumJobID),
		filepath.Join(cfg.NetworkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID),
	)
	unique := make([]string, 0, len(candidates))
	seen := map[string]bool{}
	for _, candidate := range candidates {
		candidate = filepath.Clean(candidate)
		if candidate == "." || seen[candidate] {
			continue
		}
		seen[candidate] = true
		unique = append(unique, candidate)
	}
	return unique
}

func safeJobFilePath(jobDir string, values ...any) string {
	candidates := make([]string, 0, len(values))
	for _, raw := range values {
		if value := strings.TrimSpace(stringValue(raw)); value != "" {
			candidates = append(candidates, value)
		}
	}
	for _, candidate := range candidates {
		if !filepath.IsAbs(candidate) {
			candidate = filepath.Join(jobDir, candidate)
		}
		absolute, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		relative, err := filepath.Rel(jobDir, absolute)
		if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
			continue
		}
		if regularFile(absolute) {
			return absolute
		}
	}
	return ""
}

func jobArtifactPath(jobDir string, values ...any) string {
	return safeJobFilePath(jobDir, append(values,
		filepath.Join(jobDir, "reassembled", "render.png"),
		filepath.Join(jobDir, "reassembled", "render.ppm"),
	)...)
}

// refreshRaytracerArtifacts records the summary and result the Rust node
// wrote for a job of any workload it runs (the name predates sha256).
func (h *Handler) refreshRaytracerArtifacts(job models.Job) models.Job {
	if _, ok := silicium.JobStorageDir(job.Workload); !ok {
		return job
	}
	if regularFile(job.ResultPath) && regularFile(job.SummaryPath) {
		return job
	}
	for _, jobDir := range raytracerJobDirectories(job) {
		summaryPath := filepath.Join(jobDir, "raytracer-summary.json")
		summary := readJSONMap(summaryPath)
		if len(summary) == 0 {
			continue
		}
		resultPath := jobArtifactPath(jobDir,
			summary["reassembled_png"],
			summary["result_png_path"],
			summary["result_path"],
			summary["reassembled_ppm"],
		)
		updates := map[string]any{"summary_path": summaryPath}
		job.SummaryPath = summaryPath
		summarySuccess, successKnown := summary["success"].(bool)
		if resultPath != "" && (!successKnown || summarySuccess) {
			updates["result_path"] = resultPath
			updates["status"] = "completed"
			updates["error_message"] = ""
			job.ResultPath = resultPath
			job.Status = "completed"
			job.ErrorMessage = ""
			units, receiptHash := verifiedBillingForJob(job)
			updates["billable_work_units"] = units
			updates["compute_receipt_hash"] = receiptHash
			job.BillableWorkUnits = units
			job.ComputeReceiptHash = receiptHash
		}
		if trace, ok := summary["devnet_trace"].(map[string]any); ok {
			if tracePath := safeJobFilePath(jobDir, trace["trace_path"]); tracePath != "" {
				updates["devnet_trace_path"] = tracePath
				job.DevnetTracePath = tracePath
			}
		}
		if h.DB != nil {
			h.DB.Model(&models.Job{}).Where("id = ?", job.ID).Updates(updates)
		}
		return job
	}
	return job
}

func progressPathForJob(job models.Job) string {
	if _, ok := silicium.JobStorageDir(job.Workload); ok {
		directories := raytracerJobDirectories(job)
		for _, directory := range directories {
			candidate := filepath.Join(directory, "raytracer-progress.json")
			if regularFile(candidate) {
				return candidate
			}
		}
		if len(directories) > 0 {
			return filepath.Join(directories[0], "raytracer-progress.json")
		}
	}
	networkRoot := envDefault("SILICIUM_NETWORK_ROOT", filepath.Clean(filepath.Join("..", "Network")))
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
