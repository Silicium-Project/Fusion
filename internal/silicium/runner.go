package silicium

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/silicium/internal/models"
)

type RunnerConfig struct {
	NetworkRoot          string
	MeshKey              string
	SeedPeers            string
	OrchestratorHost     string
	DashboardURL         string
	DevnetTrace          bool
	DevnetTxDelayMS      string
	MinComputeReputation string
	MinVerifyReputation  string
}

type RunResult struct {
	Status          string
	ResultPath      string
	SummaryPath     string
	DevnetTracePath string
	DevnetJob       string
	ErrorMessage    string
}

func ConfigFromEnv() RunnerConfig {
	networkRoot := os.Getenv("SILICIUM_NETWORK_ROOT")
	if networkRoot == "" {
		networkRoot = filepath.Clean(filepath.Join("..", "..", "Network"))
	}
	return RunnerConfig{
		NetworkRoot:          networkRoot,
		MeshKey:              envDefault("SILICIUM_MESH_KEY", "demo-mesh"),
		SeedPeers:            os.Getenv("SILICIUM_SEED_PEERS"),
		OrchestratorHost:     envDefault("SILICIUM_ORCHESTRATOR_HOST", "127.0.0.1"),
		DashboardURL:         envDefault("SILICIUM_DASHBOARD_URL", "http://localhost:5174/"),
		DevnetTrace:          envDefault("SILICIUM_DEVNET_TRACE", "1") != "0",
		DevnetTxDelayMS:      envDefault("SILICIUM_DEVNET_TX_DELAY_MS", "2500"),
		MinComputeReputation: envDefault("SILICIUM_MIN_COMPUTE_REPUTATION", "50"),
		MinVerifyReputation:  envDefault("SILICIUM_MIN_VERIFY_REPUTATION", "40"),
	}
}

func RunJob(job models.Job, cfg RunnerConfig) RunResult {
	switch strings.TrimSpace(job.Workload) {
	case "", "raytracer":
		return RunRaytracer(job, cfg)
	default:
		return RunResult{Status: "failed", ErrorMessage: "unsupported workload"}
	}
}

func RunRaytracer(job models.Job, cfg RunnerConfig) RunResult {
	if strings.TrimSpace(cfg.SeedPeers) == "" {
		return RunResult{Status: "failed", ErrorMessage: "SILICIUM_SEED_PEERS is required"}
	}
	networkRoot, err := filepath.Abs(cfg.NetworkRoot)
	if err != nil {
		return RunResult{Status: "failed", ErrorMessage: err.Error()}
	}
	if _, err := os.Stat(networkRoot); err != nil {
		return RunResult{Status: "failed", ErrorMessage: fmt.Sprintf("network root not found: %s", networkRoot)}
	}
	args := []string{
		"workloads/raytracer/run_network_job.py",
		job.InputPath,
		"--job-id", job.SiliciumJobID,
		"--node-mode", "network",
		"--network-advertise-host", cfg.OrchestratorHost,
		"--network-seed-peers", cfg.SeedPeers,
		"--network-mesh-key", cfg.MeshKey,
		"--min-compute-reputation", cfg.MinComputeReputation,
		"--min-verify-reputation", cfg.MinVerifyReputation,
	}
	if cfg.DevnetTrace {
		args = append(args, "--devnet-trace", "--devnet-tx-delay-ms", cfg.DevnetTxDelayMS)
	}
	cmd := pythonCommand(networkRoot, args...)
	output, err := cmd.CombinedOutput()
	summaryPath := filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "raytracer-summary.json")
	result := parseRaytracerSummary(summaryPath)
	result.SummaryPath = summaryPath
	if result.DevnetTracePath == "" {
		tracePath := filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "devnet-trace.json")
		if _, statErr := os.Stat(tracePath); statErr == nil {
			result.DevnetTracePath = tracePath
		}
	}
	if result.ResultPath == "" {
		pngPath := filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "reassembled", "render.png")
		outputPath := filepath.Join(networkRoot, ".silicium", "jobs", "raytracer", job.SiliciumJobID, "reassembled", "render.ppm")
		if _, statErr := os.Stat(pngPath); statErr == nil {
			result.ResultPath = pngPath
		} else if _, statErr := os.Stat(outputPath); statErr == nil {
			result.ResultPath = outputPath
		}
	}
	if err != nil {
		result.Status = "failed"
		result.ErrorMessage = strings.TrimSpace(string(output))
		if result.ErrorMessage == "" {
			result.ErrorMessage = err.Error()
		}
		return result
	}
	if result.Status == "" {
		result.Status = "completed"
	}
	return result
}

func NewJobID(userID uint) string {
	return fmt.Sprintf("site-render-%d-%d", userID, time.Now().UnixNano())
}

func pythonCommand(networkRoot string, args ...string) *exec.Cmd {
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.Command("py", args...)
	} else {
		fullArgs := append([]string{}, args...)
		cmd = exec.Command("python3", fullArgs...)
	}
	cmd.Dir = networkRoot
	return cmd
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
	if value, ok := payload["reassembled_png"].(string); ok {
		result.ResultPath = value
	} else if value, ok := payload["result_png_path"].(string); ok {
		result.ResultPath = value
	} else if value, ok := payload["result_path"].(string); ok {
		result.ResultPath = value
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
