// Anchoring a finished job: build the proof, send the memo, write the trace.

package chainproof

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// TraceFileName is written next to the job summary.
const TraceFileName = "devnet-trace.json"

// TraceSchema names the format of the trace file.
const TraceSchema = "silicium.chain-trace.v1"

// Trace statuses.
const (
	StatusPending  = "pending"
	StatusAnchored = "anchored"
	StatusFailed   = "failed"
)

// Config says whether and where jobs are anchored.
type Config struct {
	Enabled        bool
	RPCURL         string
	WalletPath     string
	ConfirmTimeout time.Duration
}

// ConfigFromEnv reads SILICIUM_DEVNET_TRACE (1/true enables),
// SILICIUM_SOLANA_RPC, SILICIUM_SOLANA_WALLET and
// SILICIUM_DEVNET_CONFIRM_TIMEOUT_S (default 90).
func ConfigFromEnv() Config {
	enabled := strings.ToLower(strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_TRACE")))
	rpcURL := strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_RPC"))
	if rpcURL == "" {
		rpcURL = "https://api.devnet.solana.com"
	}
	timeout := 90 * time.Second
	if seconds, err := strconv.Atoi(strings.TrimSpace(os.Getenv("SILICIUM_DEVNET_CONFIRM_TIMEOUT_S"))); err == nil && seconds > 0 {
		timeout = time.Duration(seconds) * time.Second
	}
	return Config{
		Enabled:        enabled == "1" || enabled == "true" || enabled == "yes",
		RPCURL:         rpcURL,
		WalletPath:     strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_WALLET")),
		ConfirmTimeout: timeout,
	}
}

// ProvedTask is a leaf with its hash and inclusion proof.
type ProvedTask struct {
	Task
	LeafHash string      `json:"leaf_hash"`
	Proof    []ProofStep `json:"proof"`
}

// Trace is the content of devnet-trace.json, read by the job dashboard.
type Trace struct {
	Schema      string       `json:"schema"`
	Status      string       `json:"status"`
	OK          bool         `json:"ok"`
	Enabled     bool         `json:"enabled"`
	Job         string       `json:"job"`
	Workload    string       `json:"workload"`
	ProgramID   string       `json:"program_id"`
	RPC         string       `json:"rpc"`
	Cluster     string       `json:"cluster"`
	Payer       string       `json:"payer"`
	Signatures  []string     `json:"signatures"`
	ExplorerURL string       `json:"explorer_url,omitempty"`
	Memo        string       `json:"memo"`
	MerkleRoot  string       `json:"merkle_root"`
	FinalSHA256 string       `json:"final_sha256"`
	ReceiptSet  string       `json:"receipt_set_hash"`
	TaskCount   int          `json:"task_count"`
	Tasks       []ProvedTask `json:"fragments"`
	UpdatedUTC  string       `json:"updated_utc"`
	Error       string       `json:"error,omitempty"`
}

// BuildTrace computes leaves, proofs, root and memo of manifest (no network).
func BuildTrace(manifest Manifest) (Trace, error) {
	leaves := make([]string, len(manifest.Tasks))
	for i, task := range manifest.Tasks {
		leaf, err := LeafHash(task)
		if err != nil {
			return Trace{}, err
		}
		leaves[i] = leaf
	}
	root, err := MerkleRoot(leaves)
	if err != nil {
		return Trace{}, err
	}
	tasks := make([]ProvedTask, len(manifest.Tasks))
	for i, task := range manifest.Tasks {
		proof, err := MerkleProof(leaves, i)
		if err != nil {
			return Trace{}, err
		}
		tasks[i] = ProvedTask{Task: task, LeafHash: leaves[i], Proof: proof}
	}
	return Trace{
		Schema:      TraceSchema,
		Status:      StatusPending,
		Enabled:     true,
		Job:         manifest.JobID,
		Workload:    manifest.Workload,
		ProgramID:   MemoProgramID,
		Signatures:  []string{},
		Memo:        MemoText(manifest, root),
		MerkleRoot:  root,
		FinalSHA256: manifest.FinalSHA256,
		ReceiptSet:  manifest.ReceiptSetHash,
		TaskCount:   len(tasks),
		Tasks:       tasks,
	}, nil
}

// MemoText is the on-chain text: schema, job, task count, root, final hash.
// The job id is cut to 96 characters so the memo always fits.
func MemoText(manifest Manifest, root string) string {
	job := manifest.JobID
	if len(job) > 96 {
		job = job[:96]
	}
	return fmt.Sprintf("%s job=%s tasks=%d root=%s final=%s",
		ManifestSchema, job, len(manifest.Tasks), root, manifest.FinalSHA256)
}

// Anchor proves the job whose summary is at summaryPath and whose final
// result is at resultPath. It writes a pending trace first, so the site shows
// the tree even if the chain is slow, then the anchored or failed one. The
// returned path is the trace file; the error says why anchoring failed.
func Anchor(ctx context.Context, cfg Config, summaryPath, resultPath string) (string, Trace, error) {
	tracePath := filepath.Join(filepath.Dir(summaryPath), TraceFileName)
	trace, err := prepare(summaryPath, resultPath)
	if err != nil {
		return "", Trace{}, err
	}
	trace.RPC = rpcOrigin(cfg.RPCURL)
	trace.Cluster = Cluster(cfg.RPCURL)
	if err := writeTrace(tracePath, &trace); err != nil {
		return "", trace, err
	}
	signature, payer, err := send(ctx, cfg, trace.Memo)
	trace.Payer = payer
	if err != nil {
		trace.Status, trace.OK, trace.Error = StatusFailed, false, err.Error()
		if signature != "" {
			trace.Signatures = []string{signature}
		}
	} else {
		trace.Status, trace.OK = StatusAnchored, true
		trace.Signatures = []string{signature}
		trace.ExplorerURL = ExplorerURL(signature, trace.Cluster)
	}
	if writeErr := writeTrace(tracePath, &trace); writeErr != nil && err == nil {
		err = writeErr
	}
	return tracePath, trace, err
}

// prepare reads the summary, hashes the result and builds the trace.
func prepare(summaryPath, resultPath string) (Trace, error) {
	raw, err := os.ReadFile(summaryPath)
	if err != nil {
		return Trace{}, fmt.Errorf("chainproof: read summary: %w", err)
	}
	var summary map[string]any
	if err := json.Unmarshal(raw, &summary); err != nil {
		return Trace{}, errors.New("chainproof: the job summary is not JSON")
	}
	finalHash, err := fileSHA256(resultPath)
	if err != nil {
		return Trace{}, err
	}
	manifest, err := ManifestFromSummary(summary, finalHash)
	if err != nil {
		return Trace{}, err
	}
	return BuildTrace(manifest)
}

// send signs and submits the memo, then waits for confirmation. The
// signature is returned even when confirmation fails, so it can be checked.
func send(ctx context.Context, cfg Config, memo string) (string, string, error) {
	if cfg.WalletPath == "" {
		return "", "", errors.New("chainproof: SILICIUM_SOLANA_WALLET is not set")
	}
	key, err := LoadKeypair(cfg.WalletPath)
	if err != nil {
		return "", "", err
	}
	payer := Base58Encode(key.Public().(ed25519.PublicKey))
	rpc := RPC{URL: cfg.RPCURL}
	blockhash, err := rpc.LatestBlockhash(ctx)
	if err != nil {
		return "", payer, err
	}
	wire, signature, err := MemoTransaction(key, blockhash, memo)
	if err != nil {
		return "", payer, err
	}
	if _, err := rpc.SendTransaction(ctx, wire); err != nil {
		return "", payer, err
	}
	confirmCtx, cancel := context.WithTimeout(ctx, cfg.ConfirmTimeout)
	defer cancel()
	return signature, payer, rpc.WaitConfirmed(confirmCtx, signature, 1500*time.Millisecond)
}

func fileSHA256(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", fmt.Errorf("chainproof: open result: %w", err)
	}
	defer file.Close()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", fmt.Errorf("chainproof: hash result: %w", err)
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}

// rpcOrigin keeps only scheme and host: RPC URLs often embed an API key.
func rpcOrigin(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Host == "" {
		return "configured RPC endpoint"
	}
	return parsed.Scheme + "://" + parsed.Host
}

// writeTrace stamps and atomically writes the trace file.
func writeTrace(path string, trace *Trace) error {
	trace.UpdatedUTC = time.Now().UTC().Format(time.RFC3339)
	data, err := json.MarshalIndent(trace, "", "  ")
	if err != nil {
		return err
	}
	temporary := path + ".tmp"
	if err := os.WriteFile(temporary, data, 0o640); err != nil {
		return fmt.Errorf("chainproof: write trace: %w", err)
	}
	return os.Rename(temporary, path)
}
