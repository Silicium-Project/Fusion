package silicium

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/silicium/internal/models"
)

type RunnerConfig struct {
	NetworkRoot           string
	OrchestratorExportDir string
	OrchestratorNodeID    string
	MeshKey               string
	SeedPeers             string
	OrchestratorHost      string
	DashboardURL          string
	DevnetTraceMode       string
	DevnetTxDelayMS       string
	DevnetTraceTimeoutS   string
	SolanaRPC             string
	SolanaProgramID       string
	SolanaWallet          string
	MinComputeReputation  string
	MinVerifyReputation   string
}

type RunResult struct {
	Status          string
	ResultPath      string
	SummaryPath     string
	DevnetTracePath string
	DevnetJob       string
	ErrorMessage    string
}

type CompactTraceResult struct {
	Path      string
	Signature string
	Status    string
	Error     string
}

func ConfigFromEnv() RunnerConfig {
	networkRoot := os.Getenv("SILICIUM_NETWORK_ROOT")
	if networkRoot == "" {
		networkRoot = filepath.Clean(filepath.Join("..", "..", "Network"))
	}
	return RunnerConfig{
		NetworkRoot:           networkRoot,
		OrchestratorExportDir: os.Getenv("SILICIUM_ORCHESTRATOR_EXPORT_DIR"),
		OrchestratorNodeID:    envDefault("SILICIUM_ORCHESTRATOR_NODE_ID", "orchestrator-1"),
		MeshKey:               envDefault("SILICIUM_MESH_KEY", "demo-mesh"),
		SeedPeers:             os.Getenv("SILICIUM_SEED_PEERS"),
		OrchestratorHost:      envDefault("SILICIUM_ORCHESTRATOR_HOST", "127.0.0.1"),
		DashboardURL:          envDefault("SILICIUM_DASHBOARD_URL", "http://localhost:5174/"),
		DevnetTraceMode:       configuredDevnetTraceMode(),
		DevnetTxDelayMS:       envDefault("SILICIUM_DEVNET_TX_DELAY_MS", "2500"),
		DevnetTraceTimeoutS:   envDefault("SILICIUM_DEVNET_TRACE_TIMEOUT_S", "240"),
		SolanaRPC:             envDefault("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"),
		SolanaProgramID:       envDefault("SILICIUM_SOLANA_PROGRAM_ID", "AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA"),
		SolanaWallet:          os.Getenv("SILICIUM_SOLANA_WALLET"),
		MinComputeReputation:  envDefault("SILICIUM_MIN_COMPUTE_REPUTATION", "50"),
		MinVerifyReputation:   envDefault("SILICIUM_MIN_VERIFY_REPUTATION", "40"),
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
	if strings.TrimSpace(cfg.OrchestratorExportDir) != "" {
		args = append(
			args,
			"--export-dir", cfg.OrchestratorExportDir,
			"--network-node-id", cfg.OrchestratorNodeID,
			"--no-network-start-orchestrator",
		)
	}
	if cfg.DevnetTraceMode == "full_demo" {
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

func configuredDevnetTraceMode() string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_TRACE_MODE")))
	switch mode {
	case "off", "async_compact", "full_demo":
		return mode
	case "compact", "async":
		return "async_compact"
	case "full", "demo":
		return "full_demo"
	case "":
		legacy := strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_TRACE"))
		if legacy == "0" {
			return "off"
		}
		if legacy == "1" {
			return "full_demo"
		}
		return "async_compact"
	default:
		return "off"
	}
}

func CompactTracePath(summaryPath string) string {
	return filepath.Join(filepath.Dir(summaryPath), "devnet-compact-trace.json")
}

func PrepareCompactDevnetTrace(summaryPath string) (string, error) {
	tracePath := CompactTracePath(summaryPath)
	payload := map[string]any{
		"schema_version":      1,
		"enabled":             true,
		"mode":                "async_compact",
		"status":              "pending",
		"ok":                  false,
		"source_summary_path": summaryPath,
		"queued_utc":          time.Now().UTC().Format(time.RFC3339),
	}
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(tracePath, data, 0o644); err != nil {
		return "", err
	}
	return tracePath, nil
}

func RunCompactDevnetTrace(summaryPath string, cfg RunnerConfig) CompactTraceResult {
	tracePath := CompactTracePath(summaryPath)
	result := CompactTraceResult{Path: tracePath, Status: "failed"}
	networkRoot, err := filepath.Abs(cfg.NetworkRoot)
	if err != nil {
		result.Error = err.Error()
		writeCompactTraceFailure(tracePath, result.Error)
		return result
	}
	solanaRoot := filepath.Join(networkRoot, "solana-layer")
	tsNode := filepath.Join(solanaRoot, "node_modules", ".bin", "ts-node")
	if runtime.GOOS == "windows" {
		tsNode += ".cmd"
	}
	timeoutSeconds, err := strconv.Atoi(cfg.DevnetTraceTimeoutS)
	if err != nil || timeoutSeconds < 30 {
		timeoutSeconds = 240
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(timeoutSeconds)*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, tsNode, "scripts/devnet_compact_trace.ts", summaryPath)
	cmd.Dir = solanaRoot
	cmd.Env = append(
		os.Environ(),
		"SOLANA_RPC_URL="+cfg.SolanaRPC,
		"SOLANA_LAYER_PROGRAM_ID="+cfg.SolanaProgramID,
		"SILICIUM_TRACE_RESULT_PATH="+tracePath,
	)
	if strings.TrimSpace(cfg.SolanaWallet) != "" {
		cmd.Env = append(cmd.Env, "ANCHOR_WALLET="+cfg.SolanaWallet)
	}
	_, runErr := cmd.CombinedOutput()
	if runErr != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			result.Error = "compact devnet trace timed out"
		} else {
			result.Error = "compact devnet trace failed: " + runErr.Error()
		}
		writeCompactTraceFailure(tracePath, result.Error)
		return result
	}

	data, readErr := os.ReadFile(tracePath)
	if readErr != nil {
		result.Error = readErr.Error()
		return result
	}
	var trace map[string]any
	if err := json.Unmarshal(data, &trace); err != nil {
		result.Error = err.Error()
		return result
	}
	if signature, ok := trace["signature"].(string); ok {
		result.Signature = signature
	}
	if status, ok := trace["status"].(string); ok {
		result.Status = status
	}
	if okValue, _ := trace["ok"].(bool); !okValue || result.Status != "confirmed" {
		result.Error = "compact devnet trace was not confirmed"
	}
	return result
}

func writeCompactTraceFailure(tracePath string, message string) {
	payload := map[string]any{}
	if data, err := os.ReadFile(tracePath); err == nil {
		_ = json.Unmarshal(data, &payload)
	}
	if existing, ok := payload["error"].(string); ok && strings.TrimSpace(existing) != "" && strings.HasPrefix(message, "compact devnet trace failed:") {
		message = existing
	}
	payload["schema_version"] = 1
	payload["enabled"] = true
	payload["mode"] = "async_compact"
	payload["status"] = "failed"
	payload["ok"] = false
	payload["error"] = message
	payload["failed_utc"] = time.Now().UTC().Format(time.RFC3339)
	if data, err := json.MarshalIndent(payload, "", "  "); err == nil {
		_ = os.WriteFile(tracePath, data, 0o644)
	}
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
