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

type RunnerConfig struct {
	NetworkRoot           string
	MeshKey               string
	SeedPeers             string
	OrchestratorNodeID    string
	OrchestratorHost      string
	EmitterPort           string
	OrchestratorExportDir string
	DashboardURL          string
	DevnetTrace           bool
	DevnetTxDelayMS       string
	MinComputeReputation  string
	MinVerifyReputation   string
	ControlURL            string
	IdentityKeyPath       string
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
		networkRoot = filepath.Clean(filepath.Join("..", "..", "Network"))
	}
	return RunnerConfig{
		NetworkRoot:           networkRoot,
		MeshKey:               envDefault("SILICIUM_MESH_KEY", "demo-mesh"),
		SeedPeers:             os.Getenv("SILICIUM_SEED_PEERS"),
		OrchestratorNodeID:    envDefault("SILICIUM_ORCHESTRATOR_NODE_ID", "orchestrator-1"),
		OrchestratorHost:      envDefault("SILICIUM_ORCHESTRATOR_HOST", "127.0.0.1"),
		EmitterPort:           envDefault("SILICIUM_EMITTER_PORT", "46102"),
		OrchestratorExportDir: envDefault("SILICIUM_ORCHESTRATOR_EXPORT_DIR", filepath.Join(networkRoot, ".silicium", "networked", "orchestrator", "export")),
		DashboardURL:          envDefault("SILICIUM_DASHBOARD_URL", "http://localhost:5174/"),
		DevnetTrace:           envDefault("SILICIUM_DEVNET_TRACE", "1") != "0",
		DevnetTxDelayMS:       envDefault("SILICIUM_DEVNET_TX_DELAY_MS", "2500"),
		MinComputeReputation:  envDefault("SILICIUM_MIN_COMPUTE_REPUTATION", "50"),
		MinVerifyReputation:   envDefault("SILICIUM_MIN_VERIFY_REPUTATION", "40"),
		ControlURL:            envDefault("SILICIUM_CONTROL_URL", "http://127.0.0.1:46100/gossip/publish"),
		IdentityKeyPath:       envDefault("SILICIUM_ORCHESTRATOR_IDENTITY_KEY", "/var/lib/silicium/network/orchestrator/state/peer_identity_ed25519.pem"),
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
	args := raytracerArgs(job, cfg)
	cmd := pythonCommand(ctx, networkRoot, args...)
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
	if result.Status == "" {
		result.Status = "completed"
	}
	return result
}

func raytracerArgs(job models.Job, cfg RunnerConfig) []string {
	args := []string{
		"workloads/raytracer/run_network_job.py",
		job.InputPath,
		"--job-id", job.SiliciumJobID,
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
	if cfg.DevnetTrace {
		args = append(args, "--devnet-trace", "--devnet-tx-delay-ms", cfg.DevnetTxDelayMS)
	}
	return args
}

func NewJobID(userID uint) string {
	return fmt.Sprintf("site-render-%d-%d", userID, time.Now().UnixNano())
}

func pythonCommand(ctx context.Context, networkRoot string, args ...string) *exec.Cmd {
	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.CommandContext(ctx, "py", args...)
	} else {
		fullArgs := append([]string{}, args...)
		cmd = exec.CommandContext(ctx, "python3", fullArgs...)
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
