package silicium

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
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
	// Used only when rendering historical imported RPC summaries. All new
	// Network traffic uses the Rust node control API.
	OrchestratorExportDir string
	WorkloadStorageDir    string
	DevnetTrace           bool
	DevnetTxDelayMS       string
	MinComputeReputation  string
	MinVerifyReputation   string
	ControlURL            string
	IdentityKeyPath       string
	DashboardURL          string
	NodeAPIURL            string
	NodeControlToken      string
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
		// Devnet settlement is an explicit write operation. Keep it opt-in so a
		// backend without a funded wallet cannot accidentally publish or pay a
		// trace during a normal render.
		DevnetTrace:          envDefault("SILICIUM_DEVNET_TRACE", "0") == "1",
		DevnetTxDelayMS:      envDefault("SILICIUM_DEVNET_TX_DELAY_MS", "2500"),
		MinComputeReputation: envDefault("SILICIUM_MIN_COMPUTE_REPUTATION", "50"),
		MinVerifyReputation:  envDefault("SILICIUM_MIN_VERIFY_REPUTATION", "40"),
		ControlURL:           envDefault("SILICIUM_CONTROL_URL", "http://127.0.0.1:46100/gossip/publish"),
		IdentityKeyPath:      envDefault("SILICIUM_ORCHESTRATOR_IDENTITY_KEY", "/var/lib/silicium/network/orchestrator/state/peer_identity_ed25519.pem"),
		DashboardURL:         envDefault("SILICIUM_DASHBOARD_URL", "http://localhost:5174/"),
		NodeAPIURL:           envDefault("SILICIUM_NODE_API_URL", "http://127.0.0.1:9092"),
		NodeControlToken:     os.Getenv("SILICIUM_NODE_CONTROL_TOKEN"),
		ReleaseChannel:       release.Current().Channel,
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

func RunJob(ctx context.Context, job models.Job, cfg RunnerConfig) RunResult {
	switch strings.TrimSpace(job.Workload) {
	case "", "raytracer":
		return RunRaytracer(ctx, job, cfg)
	default:
		return RunResult{Status: "failed", ErrorMessage: "unsupported workload"}
	}
}

func RunRaytracer(ctx context.Context, job models.Job, cfg RunnerConfig) RunResult {
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
	raytracerRoot := filepath.Join(workloadRoot, "raytracer", job.SiliciumJobID)
	outputPath := filepath.Join(raytracerRoot, "reassembled", "render.ppm")
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o750); err != nil {
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	_, err = SubmitControlTask(ctx, cfg, ControlTaskSubmission{
		TaskID:        job.SiliciumJobID,
		RootJobID:     job.SiliciumJobID,
		Workload:      "raytracer",
		RequiredRoles: []string{"compute", "verify"},
		ScenePath:     job.InputPath,
		OutputPath:    outputPath,
		Seed:          job.SiliciumJobID,
	})
	if err != nil {
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
	result := RunResult{Status: "completed", ResultPath: outputPath, ComputeReceiptHash: task.ResultHash}
	return validateRaytracerCompletion(result)
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

func ValidateWorkload(workload string) error {
	if workload == "" || workload == "raytracer" {
		return nil
	}
	return errors.New("unsupported workload")
}
