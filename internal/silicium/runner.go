package silicium

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/release"
)

type RunnerConfig struct {
	NetworkRoot        string
	OrchestratorNodeID string
	// Export directory of the orchestrator node: heartbeat and peer files
	// read by the network endpoints.
	OrchestratorExportDir string
	WorkloadStorageDir    string
	NodeAPIURL            string
	NodeControlToken      string
	// NodeContainerDataRoot is the path used by the BackEnd container for the
	// shared data mount. NodeHostDataRoot is the corresponding path seen by the
	// host-side Rust node. They differ on the dev channel because
	// /var/lib/silicium-dev is mounted as /var/lib/silicium in the container.
	NodeContainerDataRoot string
	NodeHostDataRoot      string
	ReleaseChannel        string
}

type RunResult struct {
	Status             string
	ResultPath         string
	SummaryPath        string
	DevnetTracePath    string
	DevnetJob          string
	ErrorMessage       string
	BillableWorkUnits  uint64
	ComputeReceiptHash string
}

func ConfigFromEnv() RunnerConfig {
	networkRoot := os.Getenv("SILICIUM_NETWORK_ROOT")
	if networkRoot == "" {
		// BackEnd and Network are sibling repositories in the local Fusion
		// checkout. Production sets an absolute path explicitly.
		networkRoot = filepath.Clean(filepath.Join("..", "Network"))
	}
	return RunnerConfig{
		NetworkRoot:           networkRoot,
		OrchestratorNodeID:    envDefault("SILICIUM_ORCHESTRATOR_NODE_ID", "orchestrator-1"),
		OrchestratorExportDir: envDefault("SILICIUM_ORCHESTRATOR_EXPORT_DIR", filepath.Join(networkRoot, ".silicium", "networked", "orchestrator", "export")),
		WorkloadStorageDir:    envDefault("SILICIUM_WORKLOAD_STORAGE_DIR", filepath.Join(networkRoot, ".silicium", "jobs")),
		NodeAPIURL:            envDefault("SILICIUM_NODE_API_URL", "http://127.0.0.1:9092"),
		NodeControlToken:      os.Getenv("SILICIUM_NODE_CONTROL_TOKEN"),
		NodeContainerDataRoot: envDefault("SILICIUM_NODE_CONTAINER_DATA_ROOT", "/var/lib/silicium"),
		NodeHostDataRoot:      os.Getenv("SILICIUM_NODE_HOST_DATA_ROOT"),
		ReleaseChannel:        release.Current().Channel,
	}
}

type TaskControl struct {
	ControlID      string `json:"control_id"`
	RootJobID      string `json:"root_job_id"`
	Action         string `json:"action"`
	Reason         string `json:"reason"`
	IssuerNode     string `json:"issuer_node_id"`
	IssuedUTC      string `json:"issued_utc"`
	DeadlineUTC    string `json:"deadline_utc,omitempty"`
	ReleaseChannel string `json:"release_channel,omitempty"`
}

func PublishTaskControl(ctx context.Context, cfg RunnerConfig, control TaskControl) error {
	switch strings.TrimSpace(control.Action) {
	case "cancel", "expire":
		_, err := CancelControlWorkload(ctx, cfg, control.RootJobID)
		return err
	default:
		return fmt.Errorf("unsupported Rust node control action: %s", control.Action)
	}
}

// RunJob submits a job to the Rust node and waits for its result.
func RunJob(ctx context.Context, job models.Job, cfg RunnerConfig) RunResult {
	spec, ok := workloadSpecFor(job.Workload)
	if !ok {
		return RunResult{Status: "failed", ErrorMessage: "unsupported workload"}
	}
	return runNodeJob(ctx, job, cfg, spec)
}

// RunRaytracer runs a raytracer job (kept for callers that name it).
func RunRaytracer(ctx context.Context, job models.Job, cfg RunnerConfig) RunResult {
	return runNodeJob(ctx, job, cfg, raytracerSpec)
}

// runNodeJob submits `job` as a workload of `spec`, waits until every
// fragment is finalized, then until the node has assembled the result.
func runNodeJob(ctx context.Context, job models.Job, cfg RunnerConfig, spec workloadSpec) RunResult {
	networkRoot, err := filepath.Abs(cfg.NetworkRoot)
	if err != nil {
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	if _, err := os.Stat(networkRoot); err != nil {
		return RunResult{Status: "failed", ErrorMessage: fmt.Sprintf("network root not found: %s", networkRoot)}
	}
	workloadRoot := strings.TrimSpace(cfg.WorkloadStorageDir)
	if workloadRoot == "" {
		workloadRoot = filepath.Join(networkRoot, ".silicium", "jobs")
	} else if !filepath.IsAbs(workloadRoot) {
		workloadRoot = filepath.Join(networkRoot, workloadRoot)
	}
	workloadRoot, err = filepath.Abs(workloadRoot)
	if err != nil {
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	jobRoot := filepath.Join(workloadRoot, spec.StorageDir, job.SiliciumJobID)
	outputPath := filepath.Join(jobRoot, filepath.FromSlash(spec.ResultFile))
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o750); err != nil {
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	scenePath := nodeVisiblePath(job.InputPath, cfg)
	_, err = SubmitControlTask(ctx, cfg, ControlTaskSubmission{
		TaskID:        job.SiliciumJobID,
		RootJobID:     job.SiliciumJobID,
		Workload:      spec.NodeID,
		RequiredRoles: []string{"compute", "verify"},
		ScenePath:     scenePath,
		OutputPath:    outputPath,
		Seed:          job.SiliciumJobID,
		FragmentCount: job.FragmentCount,
	})
	if err != nil {
		// The node refuses unreadable documents with a message for the user.
		var refused *ControlError
		if errors.As(err, &refused) && refused.Status == http.StatusBadRequest && IsDocumentSearch(job.Workload) {
			return RunResult{Status: "failed", ErrorMessage: refused.Message}
		}
		return RunResult{Status: "failed", ErrorMessage: "rust_node_submission_failed: " + err.Error()}
	}
	task, err := waitForControlTask(ctx, cfg, job.SiliciumJobID)
	if err != nil {
		if cause := context.Cause(ctx); cause != nil {
			_, _ = CancelControlWorkload(context.Background(), cfg, job.SiliciumJobID)
			return RunResult{Status: "cancelled", ErrorMessage: cause.Error()}
		}
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	// Finalized fragments are not the result yet: wait for the node to
	// download the fragment results from the workers and assemble them.
	// The node names the summary file the same way for every workload.
	summaryPath := filepath.Join(jobRoot, "raytracer-summary.json")
	if err := waitForReassembledImage(ctx, outputPath, summaryPath, resultWaitTimeout()); err != nil {
		if cause := context.Cause(ctx); cause != nil {
			return RunResult{Status: "cancelled", ErrorMessage: cause.Error()}
		}
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	result := RunResult{Status: "completed", ResultPath: outputPath, SummaryPath: summaryPath, ComputeReceiptHash: task.ResultHash}
	return validateRaytracerCompletion(result)
}

// nodeVisiblePath translates a shared-volume path from the BackEnd container
// namespace to the host namespace used by the Rust node. When both processes
// run in the same namespace, or when the path is outside the configured mount,
// it returns the original path unchanged.
func nodeVisiblePath(inputPath string, cfg RunnerConfig) string {
	containerRoot := strings.TrimRight(strings.TrimSpace(cfg.NodeContainerDataRoot), "/\\")
	hostRoot := strings.TrimRight(strings.TrimSpace(cfg.NodeHostDataRoot), "/\\")
	if containerRoot == "" || hostRoot == "" || containerRoot == hostRoot {
		return inputPath
	}

	path := strings.TrimSpace(inputPath)
	for _, separator := range []string{"/", "\\"} {
		prefix := containerRoot + separator
		if strings.HasPrefix(path, prefix) {
			relative := strings.TrimLeft(strings.TrimPrefix(path, prefix), "/\\")
			return filepath.Join(hostRoot, filepath.FromSlash(strings.ReplaceAll(relative, "\\", "/")))
		}
	}
	if path == containerRoot {
		return hostRoot
	}
	return inputPath
}

func waitForControlTask(ctx context.Context, cfg RunnerConfig, rootJobID string) (ControlTask, error) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		tasks, err := ListControlTasks(ctx, cfg, rootJobID)
		if err != nil {
			return ControlTask{}, err
		}
		if len(tasks) > 0 {
			var firstCompleted ControlTask
			allCompleted := true
			for _, task := range tasks {
				switch strings.ToLower(strings.TrimSpace(task.Status)) {
				case "verified", "completed", "finalized":
					if firstCompleted.TaskID == "" {
						firstCompleted = task
					}
				case "failed", "cancelled", "expired":
					message := strings.TrimSpace(task.Error)
					if message == "" {
						message = "rust_node_task_" + strings.ToLower(task.Status)
					}
					return ControlTask{}, fmt.Errorf("%s", message)
				default:
					allCompleted = false
				}
			}
			if allCompleted && firstCompleted.TaskID != "" {
				return firstCompleted, nil
			}
		}
		select {
		case <-ctx.Done():
			return ControlTask{}, ctx.Err()
		case <-ticker.C:
		}
	}
}

func NewJobID(userID uint) string {
	return fmt.Sprintf("site-render-%d-%d", userID, time.Now().UnixNano())
}

func parseRaytracerSummary(summaryPath string) RunResult {
	data, err := os.ReadFile(summaryPath)
	if err != nil {
		return RunResult{}
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return RunResult{}
	}
	result := RunResult{Status: "completed"}
	if success, ok := payload["success"].(bool); ok && !success {
		result.Status = "failed"
		for _, key := range []string{"failure_detail", "error", "error_message"} {
			if value, ok := payload[key].(string); ok && strings.TrimSpace(value) != "" {
				result.ErrorMessage = strings.TrimSpace(value)
				break
			}
		}
	}
	for _, key := range []string{"reassembled_png", "result_png_path", "result_path", "reassembled_ppm"} {
		if value, ok := payload[key].(string); ok && strings.TrimSpace(value) != "" {
			result.ResultPath = value
			break
		}
	}
	if trace, ok := payload["devnet_trace"].(map[string]any); ok {
		if path, ok := trace["trace_path"].(string); ok {
			result.DevnetTracePath = path
		}
		if inner, ok := trace["trace"].(map[string]any); ok {
			if job, ok := inner["job"].(string); ok {
				result.DevnetJob = job
			}
		}
		if okValue, ok := trace["ok"].(bool); ok && !okValue {
			result.Status = "failed"
			result.ErrorMessage = "devnet trace failed"
			if msg, ok := trace["error"].(string); ok && strings.TrimSpace(msg) != "" {
				result.ErrorMessage = msg
			}
		}
	}
	if billing, ok := payload["billing"].(map[string]any); ok {
		if units, ok := billing["billable_work_units"].(float64); ok && units >= 0 {
			result.BillableWorkUnits = uint64(units)
		}
		if receiptHash, ok := billing["receipt_set_hash"].(string); ok {
			result.ComputeReceiptHash = receiptHash
		}
	}
	return result
}

func validateRaytracerCompletion(result RunResult) RunResult {
	if result.Status == "" {
		result.Status = "failed"
		result.ErrorMessage = "raytracer_summary_missing"
		return result
	}
	if result.Status != "completed" {
		return result
	}
	if strings.TrimSpace(result.ResultPath) == "" {
		result.Status = "failed"
		result.ErrorMessage = "raytracer_result_missing"
		return result
	}
	info, err := os.Stat(result.ResultPath)
	if err != nil || !info.Mode().IsRegular() {
		result.Status = "failed"
		result.ErrorMessage = "raytracer_result_unreadable: " + result.ResultPath
	}
	return result
}

func envDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}
