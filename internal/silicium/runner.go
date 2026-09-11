package silicium

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/silicium/internal/models"
)

var lookPath = exec.LookPath

type RunnerConfig struct {
	NetworkRoot           string
	MeshKey               string
	SeedPeers             string
	OrchestratorNodeID    string
	OrchestratorHost      string
	EmitterPort           string
	OrchestratorExportDir string
	WorkloadStorageDir    string
	DashboardURL          string
	DevnetTraceMode       string
	DevnetTraceTimeoutS   string
	DevnetTxDelayMS       string
	MinComputeReputation  string
	MinVerifyReputation   string
	ControlURL            string
	IdentityKeyPath       string
}

const (
	DevnetTraceModeOff          = "off"
	DevnetTraceModeAsyncCompact = "async_compact"
	DevnetTraceModeFullDemo     = "full_demo"
)

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
		MeshKey:               envDefault("SILICIUM_MESH_KEY", "demo-mesh"),
		SeedPeers:             os.Getenv("SILICIUM_SEED_PEERS"),
		OrchestratorNodeID:    envDefault("SILICIUM_ORCHESTRATOR_NODE_ID", "orchestrator-1"),
		OrchestratorHost:      envDefault("SILICIUM_ORCHESTRATOR_HOST", "127.0.0.1"),
		EmitterPort:           envDefault("SILICIUM_EMITTER_PORT", "46102"),
		OrchestratorExportDir: envDefault("SILICIUM_ORCHESTRATOR_EXPORT_DIR", filepath.Join(networkRoot, ".silicium", "networked", "orchestrator", "export")),
		WorkloadStorageDir:    envDefault("SILICIUM_WORKLOAD_STORAGE_DIR", filepath.Join(networkRoot, ".silicium", "jobs")),
		DashboardURL:          envDefault("SILICIUM_DASHBOARD_URL", "http://localhost:5174/"),
		DevnetTraceMode:       configuredDevnetTraceMode(),
		DevnetTraceTimeoutS:   envDefault("SILICIUM_DEVNET_TRACE_TIMEOUT_S", "240"),
		DevnetTxDelayMS:       envDefault("SILICIUM_DEVNET_TX_DELAY_MS", "2500"),
		MinComputeReputation:  envDefault("SILICIUM_MIN_COMPUTE_REPUTATION", "50"),
		MinVerifyReputation:   envDefault("SILICIUM_MIN_VERIFY_REPUTATION", "40"),
		ControlURL:            envDefault("SILICIUM_CONTROL_URL", "http://127.0.0.1:46100/gossip/publish"),
		IdentityKeyPath:       envDefault("SILICIUM_ORCHESTRATOR_IDENTITY_KEY", "/var/lib/silicium/network/orchestrator/state/peer_identity_ed25519.pem"),
	}
}

func configuredDevnetTraceMode() string {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_TRACE_MODE")))
	switch mode {
	case DevnetTraceModeOff, DevnetTraceModeAsyncCompact, DevnetTraceModeFullDemo:
		return mode
	case "":
		// Preserve compatibility with installations created before trace modes
		// were introduced. A configured mode always takes precedence over this
		// legacy switch so stale SILICIUM_DEVNET_TRACE=0 values cannot disable it.
		legacy := strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_TRACE"))
		if legacy == "0" {
			return DevnetTraceModeOff
		}
		if legacy != "" {
			return DevnetTraceModeFullDemo
		}
		return DevnetTraceModeAsyncCompact
	default:
		return mode
	}
}

type TaskControl struct {
	ControlID   string `json:"control_id"`
	RootJobID   string `json:"root_job_id"`
	Action      string `json:"action"`
	Reason      string `json:"reason"`
	IssuerNode  string `json:"issuer_node_id"`
	IssuedUTC   string `json:"issued_utc"`
	DeadlineUTC string `json:"deadline_utc,omitempty"`
}

func PublishTaskControl(ctx context.Context, cfg RunnerConfig, control TaskControl) error {
	payload, err := json.Marshal(map[string]any{"topic": "task_control", "payload": control})
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, cfg.ControlURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	if err := signPeerRequest(request, payload, cfg); err != nil {
		return err
	}
	response, err := (&http.Client{Timeout: 10 * time.Second}).Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("task control rejected: %s", response.Status)
	}
	return nil
}

func signPeerRequest(request *http.Request, body []byte, cfg RunnerConfig) error {
	privatePEM, err := os.ReadFile(cfg.IdentityKeyPath)
	if err != nil {
		return fmt.Errorf("read orchestrator identity key: %w", err)
	}
	privateBlock, _ := pem.Decode(privatePEM)
	if privateBlock == nil {
		return errors.New("orchestrator identity key is not PEM")
	}
	parsedPrivate, err := x509.ParsePKCS8PrivateKey(privateBlock.Bytes)
	if err != nil {
		return fmt.Errorf("parse orchestrator identity key: %w", err)
	}
	privateKey, ok := parsedPrivate.(ed25519.PrivateKey)
	if !ok {
		return errors.New("orchestrator identity key is not Ed25519")
	}

	publicPath := strings.TrimSuffix(cfg.IdentityKeyPath, filepath.Ext(cfg.IdentityKeyPath)) + ".pub.pem"
	publicPEM, err := os.ReadFile(publicPath)
	if err != nil {
		return fmt.Errorf("read orchestrator public key: %w", err)
	}
	publicBlock, _ := pem.Decode(publicPEM)
	if publicBlock == nil {
		return errors.New("orchestrator public key is not PEM")
	}
	parsedPublic, err := x509.ParsePKIXPublicKey(publicBlock.Bytes)
	if err != nil {
		return fmt.Errorf("parse orchestrator public key: %w", err)
	}
	publicKey, ok := parsedPublic.(ed25519.PublicKey)
	if !ok || !bytes.Equal(publicKey, privateKey.Public().(ed25519.PublicKey)) {
		return errors.New("orchestrator public key does not match private key")
	}

	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	bodyDigest := sha256.Sum256(body)
	bodyHash := hex.EncodeToString(bodyDigest[:])
	identityDigest := sha256.Sum256(publicPEM)
	identityID := hex.EncodeToString(identityDigest[:])[:32]
	signedPath := request.URL.EscapedPath()
	signingPayload := strings.Join(
		[]string{request.Method, signedPath, timestamp, bodyHash, cfg.OrchestratorNodeID, identityID},
		"\n",
	)
	signature := ed25519.Sign(privateKey, []byte(signingPayload))
	request.Header.Set("X-Silicium-Public-Key", base64.StdEncoding.EncodeToString(publicPEM))
	request.Header.Set("X-Silicium-Signature", hex.EncodeToString(signature))
	request.Header.Set("X-Silicium-Identity-Id", identityID)
	request.Header.Set("X-Silicium-Timestamp", timestamp)
	request.Header.Set("X-Silicium-Body-Hash", bodyHash)
	request.Header.Set("X-Silicium-Node-Id", cfg.OrchestratorNodeID)
	return nil
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
	raytracerRoot := filepath.Join(workloadRoot, "raytracer")
	runConfig := cfg
	runConfig.WorkloadStorageDir = workloadRoot
	args := raytracerArgs(job, runConfig)
	cmd := pythonCommand(ctx, networkRoot, args...)
	output, err := cmd.CombinedOutput()
	summaryPath := filepath.Join(raytracerRoot, job.SiliciumJobID, "raytracer-summary.json")
	result := parseRaytracerSummary(summaryPath)
	result.SummaryPath = summaryPath
	if result.DevnetTracePath == "" {
		tracePath := filepath.Join(raytracerRoot, job.SiliciumJobID, "devnet-trace.json")
		if _, statErr := os.Stat(tracePath); statErr == nil {
			result.DevnetTracePath = tracePath
		}
	}
	if result.ResultPath == "" {
		pngPath := filepath.Join(raytracerRoot, job.SiliciumJobID, "reassembled", "render.png")
		outputPath := filepath.Join(raytracerRoot, job.SiliciumJobID, "reassembled", "render.ppm")
		if _, statErr := os.Stat(pngPath); statErr == nil {
			result.ResultPath = pngPath
		} else if _, statErr := os.Stat(outputPath); statErr == nil {
			result.ResultPath = outputPath
		}
	}
	if err != nil {
		if cause := context.Cause(ctx); cause != nil {
			result.Status = "cancelled"
			result.ErrorMessage = cause.Error()
			return result
		}
		result.Status = "failed"
		result.ErrorMessage = strings.TrimSpace(string(output))
		if result.ErrorMessage == "" {
			result.ErrorMessage = err.Error()
		}
		return result
	}
	return validateRaytracerCompletion(result)
}

func raytracerArgs(job models.Job, cfg RunnerConfig) []string {
	workloadRoot := strings.TrimSpace(cfg.WorkloadStorageDir)
	if workloadRoot == "" {
		workloadRoot = filepath.Join(cfg.NetworkRoot, ".silicium", "jobs")
	}
	workloadRoot = filepath.Join(workloadRoot, "raytracer")
	args := []string{
		"workloads/raytracer/run_network_job.py",
		job.InputPath,
		"--job-id", job.SiliciumJobID,
		"--output-root", workloadRoot,
		"--node-mode", "network",
		// The persistent orchestrator owns task/result ingress. Starting an
		// embedded emitter here made the worker return URL disappear whenever
		// this runner process stopped or was restarted.
		"--no-network-start-emitter",
		"--export-dir", cfg.OrchestratorExportDir,
		"--network-node-id", cfg.OrchestratorNodeID,
		"--network-advertise-host", cfg.OrchestratorHost,
		"--network-port", cfg.EmitterPort,
		"--network-advertise-port", cfg.EmitterPort,
		"--network-seed-peers", cfg.SeedPeers,
		"--network-mesh-key", cfg.MeshKey,
		"--min-compute-reputation", cfg.MinComputeReputation,
		"--min-verify-reputation", cfg.MinVerifyReputation,
	}
	if job.FragmentCount > 0 {
		args = append(args, "--fragments", fmt.Sprintf("%d", job.FragmentCount))
	}
	if cfg.DevnetTraceMode == DevnetTraceModeFullDemo {
		args = append(args,
			"--devnet-trace",
			"--devnet-trace-timeout-s", envValueOr(cfg.DevnetTraceTimeoutS, "240"),
			"--devnet-tx-delay-ms", cfg.DevnetTxDelayMS,
		)
	}
	if job.DeadlineAt != nil {
		remaining := time.Until(*job.DeadlineAt)
		seconds := int(remaining / time.Second)
		if remaining%time.Second != 0 {
			seconds++
		}
		if seconds < 1 {
			seconds = 1
		}
		// Keep the workload timeout aligned with the API deadline. Without
		// this, a site job configured for more than five minutes was killed by
		// run_network_job.py's shorter default first.
		args = append(args,
			"--result-timeout-s", strconv.Itoa(seconds),
			"--node-timeout-s", strconv.Itoa(seconds),
		)
	}
	return args
}

type DevnetTraceResult struct {
	OK           bool
	Status       string
	TracePath    string
	DevnetJob    string
	ErrorMessage string
}

func CompactDevnetTracePath(summaryPath string) string {
	return filepath.Join(filepath.Dir(summaryPath), "devnet-trace.json")
}

func MarkCompactDevnetTracePending(summaryPath string) (string, error) {
	tracePath := CompactDevnetTracePath(summaryPath)
	err := updateDevnetTraceSummary(summaryPath, map[string]any{
		"enabled":    true,
		"ok":         false,
		"status":     "pending",
		"trace_path": tracePath,
	})
	return tracePath, err
}

func RunCompactDevnetTrace(ctx context.Context, cfg RunnerConfig, summaryPath string) DevnetTraceResult {
	tracePath := CompactDevnetTracePath(summaryPath)
	result := DevnetTraceResult{Status: "failed", TracePath: tracePath}
	networkRoot, err := filepath.Abs(cfg.NetworkRoot)
	if err != nil {
		result.ErrorMessage = "network_root_invalid"
		_ = finishCompactDevnetTrace(summaryPath, result, nil)
		return result
	}
	scriptPath := filepath.Join(networkRoot, "solana-layer", "scripts", "devnet_trace_fragments.mjs")
	if info, statErr := os.Stat(scriptPath); statErr != nil || !info.Mode().IsRegular() {
		result.ErrorMessage = "devnet_trace_script_not_found"
		_ = finishCompactDevnetTrace(summaryPath, result, nil)
		return result
	}

	cmd := exec.CommandContext(ctx, nodeBinary(), scriptPath, summaryPath)
	cmd.Dir = filepath.Join(networkRoot, "solana-layer")
	cmd.Env = append(os.Environ(), "SILICIUM_TRACE_RESULT_PATH="+tracePath)
	if _, commandErr := cmd.CombinedOutput(); commandErr != nil {
		if cause := context.Cause(ctx); cause != nil {
			result.ErrorMessage = "devnet_trace_timeout"
		} else {
			result.ErrorMessage = "devnet_trace_command_failed"
		}
		_ = finishCompactDevnetTrace(summaryPath, result, nil)
		return result
	}

	trace := readJSONFile(tracePath)
	signatures, _ := trace["signatures"].([]any)
	if len(trace) == 0 || len(signatures) == 0 {
		result.ErrorMessage = "devnet_trace_result_missing"
		_ = finishCompactDevnetTrace(summaryPath, result, trace)
		return result
	}
	result.OK = true
	result.Status = "submitted"
	if job, ok := trace["job"].(string); ok {
		result.DevnetJob = job
	}
	_ = finishCompactDevnetTrace(summaryPath, result, trace)
	return result
}

func CompactDevnetTraceReadiness(cfg RunnerConfig) (bool, string) {
	if cfg.DevnetTraceMode == DevnetTraceModeOff {
		return true, "disabled"
	}
	if cfg.DevnetTraceMode != DevnetTraceModeAsyncCompact && cfg.DevnetTraceMode != DevnetTraceModeFullDemo {
		return false, "trace_mode_invalid"
	}
	if strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_RPC")) == "" {
		return false, "rpc_missing"
	}
	if strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PROGRAM_ID")) == "" {
		return false, "program_id_missing"
	}
	walletPath := envDefault("SILICIUM_SOLANA_WALLET", filepath.Join("~", ".config", "solana", "id.json"))
	walletData, err := os.ReadFile(walletPath)
	if err != nil {
		return false, "wallet_unreadable"
	}
	var walletBytes []int
	if err := json.Unmarshal(walletData, &walletBytes); err != nil || len(walletBytes) != ed25519.PrivateKeySize {
		return false, "wallet_invalid"
	}
	for _, value := range walletBytes {
		if value < 0 || value > 255 {
			return false, "wallet_invalid"
		}
	}
	if _, err := lookPath(nodeBinary()); err != nil {
		return false, "node_missing"
	}
	networkRoot, err := filepath.Abs(cfg.NetworkRoot)
	if err != nil {
		return false, "network_root_invalid"
	}
	if info, err := os.Stat(filepath.Join(networkRoot, "solana-layer", "scripts", "devnet_trace_fragments.mjs")); err != nil || !info.Mode().IsRegular() {
		return false, "trace_script_missing"
	}
	if info, err := os.Stat(filepath.Join(networkRoot, "solana-layer", "node_modules", "@solana", "web3.js")); err != nil || !info.IsDir() {
		return false, "trace_dependencies_missing"
	}
	return true, "ready"
}

func finishCompactDevnetTrace(summaryPath string, result DevnetTraceResult, trace map[string]any) error {
	payload := map[string]any{
		"enabled":    true,
		"ok":         result.OK,
		"status":     result.Status,
		"trace_path": result.TracePath,
	}
	if result.ErrorMessage != "" {
		payload["error"] = result.ErrorMessage
	}
	if len(trace) > 0 {
		payload["trace"] = trace
	}
	return updateDevnetTraceSummary(summaryPath, payload)
}

func updateDevnetTraceSummary(summaryPath string, trace map[string]any) error {
	payload := readJSONFile(summaryPath)
	if len(payload) == 0 {
		return errors.New("raytracer_summary_missing")
	}
	payload["devnet_trace"] = trace
	encoded, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	encoded = append(encoded, '\n')
	temporaryPath := summaryPath + ".tmp"
	if err := os.WriteFile(temporaryPath, encoded, 0o600); err != nil {
		return err
	}
	if err := os.Rename(temporaryPath, summaryPath); err == nil {
		return nil
	}
	// Windows cannot atomically replace an existing destination with Rename.
	// Keep the original summary in place until the replacement bytes are ready.
	err = os.WriteFile(summaryPath, encoded, 0o600)
	_ = os.Remove(temporaryPath)
	return err
}

func readJSONFile(path string) map[string]any {
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

func nodeBinary() string {
	if override := strings.TrimSpace(os.Getenv("SILICIUM_NODE_BIN")); override != "" {
		return override
	}
	if path, err := lookPath("node"); err == nil {
		return path
	}
	return "node"
}

func envValueOr(value, fallback string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return fallback
}

func NewJobID(userID uint) string {
	return fmt.Sprintf("site-render-%d-%d", userID, time.Now().UnixNano())
}

func pythonBinary() string {
	override := strings.TrimSpace(os.Getenv("SILICIUM_PYTHON_BIN"))
	if override != "" {
		return override
	}
	candidates := []string{"python3", "python"}
	if runtime.GOOS == "windows" {
		candidates = []string{"py", "python3", "python"}
	}
	for _, candidate := range candidates {
		if path, err := lookPath(candidate); err == nil {
			return path
		}
	}
	return candidates[0]
}

func pythonCommand(ctx context.Context, networkRoot string, args ...string) *exec.Cmd {
	cmd := exec.CommandContext(ctx, pythonBinary(), args...)
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
