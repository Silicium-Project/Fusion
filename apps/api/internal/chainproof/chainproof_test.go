package chainproof

import (
	"context"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

func summaryFixture() map[string]any {
	var summary map[string]any
	_ = json.Unmarshal([]byte(`{
	  "job_id": "site-render-1-42", "workload": "raytracer",
	  "billing": {"receipt_set_hash": "receipts"},
	  "fragments": [
	    {"fragment_index": 1, "task_id": "abc.f001", "status": "completed", "result_hash": "r1",
	     "trace": {"publisher": "pub", "proposal_event": "p1", "spec_sha256": "s1", "attempt": 1,
	               "worker": "w1", "claim_event": "c1", "result_event": "e1", "result_sha256": "r1",
	               "verifiers": [{"author": "v1", "verdict": true, "verification_event": "x1", "self_verification": false}]}},
	    {"fragment_index": 0, "task_id": "abc.f000", "status": "completed", "result_hash": "r0", "worker": "w0"},
	    {"fragment_index": 2, "task_id": "abc.f002", "status": "running"}
	  ]}`), &summary)
	return summary
}

func TestManifestKeepsCompletedTasksInFragmentOrder(t *testing.T) {
	manifest, err := ManifestFromSummary(summaryFixture(), "sha256:ABCDEF")
	if err != nil {
		t.Fatal(err)
	}
	if len(manifest.Tasks) != 2 || manifest.Tasks[0].TaskID != "abc.f000" || manifest.Tasks[1].TaskID != "abc.f001" {
		t.Fatalf("unexpected tasks: %+v", manifest.Tasks)
	}
	if manifest.FinalSHA256 != "abcdef" || manifest.ReceiptSetHash != "receipts" {
		t.Fatalf("unexpected manifest: %+v", manifest)
	}
	if manifest.Tasks[0].Worker != "w0" || manifest.Tasks[1].Worker != "w1" {
		t.Fatal("worker must come from the trace, else from the fragment row")
	}
	if verdict := manifest.Tasks[1].Verifiers[0].Verdict; verdict == nil || !*verdict {
		t.Fatal("verifier verdict lost")
	}
}

func TestManifestRefusesAJobWithoutCompletedTask(t *testing.T) {
	_, err := ManifestFromSummary(map[string]any{"job_id": "j", "fragments": []any{}}, "")
	if err != ErrNoTasks {
		t.Fatalf("want ErrNoTasks, got %v", err)
	}
}

func TestEveryTaskProvesItsWayToTheRoot(t *testing.T) {
	for count := 1; count <= 9; count++ {
		leaves := make([]string, count)
		for i := range leaves {
			leaf, _ := LeafHash(Task{TaskID: fmt.Sprintf("t%d", i)})
			leaves[i] = leaf
		}
		root, err := MerkleRoot(leaves)
		if err != nil {
			t.Fatal(err)
		}
		for i := range leaves {
			proof, err := MerkleProof(leaves, i)
			if err != nil || !VerifyProof(leaves[i], proof, root) {
				t.Fatalf("count %d leaf %d: proof does not reach the root", count, i)
			}
		}
		other, _ := LeafHash(Task{TaskID: "forged"})
		proof, _ := MerkleProof(leaves, 0)
		if VerifyProof(other, proof, root) {
			t.Fatalf("count %d: a forged leaf was accepted", count)
		}
	}
}

func TestAChangedTaskChangesTheRoot(t *testing.T) {
	manifest, _ := ManifestFromSummary(summaryFixture(), "aa")
	first, _ := BuildTrace(manifest)
	manifest.Tasks[1].Worker = "somebody-else"
	second, _ := BuildTrace(manifest)
	if first.MerkleRoot == second.MerkleRoot {
		t.Fatal("the root must commit to the worker of every task")
	}
	if !strings.Contains(first.Memo, "root="+first.MerkleRoot) || !strings.Contains(first.Memo, "tasks=2") {
		t.Fatalf("memo does not carry the root: %s", first.Memo)
	}
}

func TestBase58MatchesSolanaKeys(t *testing.T) {
	zero, err := Base58Decode("11111111111111111111111111111111")
	if err != nil || len(zero) != 32 || zero[0] != 0 || zero[31] != 0 {
		t.Fatalf("system program id must decode to 32 zero bytes, got %v %v", zero, err)
	}
	memo, err := Base58Decode(MemoProgramID)
	if err != nil || len(memo) != 32 || Base58Encode(memo) != MemoProgramID {
		t.Fatal("memo program id does not round-trip")
	}
}

func TestMemoTransactionIsSignedByThePayer(t *testing.T) {
	_, key, _ := ed25519.GenerateKey(nil)
	wire, signature, err := MemoTransaction(key, MemoProgramID, "hello")
	if err != nil {
		t.Fatal(err)
	}
	message := checkMemoTransaction(t, wire, key.Public().(ed25519.PublicKey), "hello")
	if Base58Encode(ed25519.Sign(key, message)) != signature {
		t.Fatal("returned signature is not the transaction signature")
	}
}

// checkMemoTransaction decodes wire and checks layout, signer and memo.
func checkMemoTransaction(t *testing.T, wire []byte, payer ed25519.PublicKey, memo string) []byte {
	t.Helper()
	if wire[0] != 1 {
		t.Fatal("expected one signature")
	}
	signature, message := wire[1:65], wire[65:]
	if !ed25519.Verify(payer, message, signature) {
		t.Fatal("signature does not verify")
	}
	if message[0] != 1 || message[1] != 0 || message[2] != 1 || message[3] != 2 {
		t.Fatalf("unexpected header %v", message[:4])
	}
	if string(message[4:36]) != string(payer) {
		t.Fatal("fee payer is not the first account")
	}
	if !strings.HasSuffix(string(message), memo) {
		t.Fatal("memo data missing")
	}
	return message
}

// fakeRPC answers the three methods Anchor uses and records the transaction.
type fakeRPC struct {
	mu   sync.Mutex
	sent []byte
}

func (f *fakeRPC) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	var request struct {
		Method string            `json:"method"`
		Params []json.RawMessage `json:"params"`
	}
	_ = json.Unmarshal(body, &request)
	switch request.Method {
	case "getLatestBlockhash":
		fmt.Fprintf(w, `{"jsonrpc":"2.0","id":1,"result":{"value":{"blockhash":%q,"lastValidBlockHeight":9}}}`, MemoProgramID)
	case "sendTransaction":
		var encoded string
		_ = json.Unmarshal(request.Params[0], &encoded)
		wire, _ := base64.StdEncoding.DecodeString(encoded)
		f.mu.Lock()
		f.sent = wire
		f.mu.Unlock()
		fmt.Fprintf(w, `{"jsonrpc":"2.0","id":1,"result":%q}`, Base58Encode(wire[1:65]))
	case "getSignatureStatuses":
		fmt.Fprint(w, `{"jsonrpc":"2.0","id":1,"result":{"value":[{"confirmationStatus":"confirmed","err":null}]}}`)
	default:
		fmt.Fprint(w, `{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"unknown"}}`)
	}
}

func writeJobFiles(t *testing.T) (string, string) {
	t.Helper()
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	resultPath := filepath.Join(dir, "render.png")
	data, _ := json.Marshal(summaryFixture())
	if err := os.WriteFile(summaryPath, data, 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(resultPath, []byte("image"), 0o600); err != nil {
		t.Fatal(err)
	}
	return summaryPath, resultPath
}

func writeWallet(t *testing.T) (string, ed25519.PrivateKey) {
	t.Helper()
	_, key, _ := ed25519.GenerateKey(nil)
	values := make([]int, len(key))
	for i, value := range key {
		values[i] = int(value)
	}
	data, _ := json.Marshal(values)
	path := filepath.Join(t.TempDir(), "id.json")
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
	return path, key
}

func TestAnchorSendsTheRootAndWritesTheTrace(t *testing.T) {
	rpc := &fakeRPC{}
	server := httptest.NewServer(rpc)
	defer server.Close()
	summaryPath, resultPath := writeJobFiles(t)
	wallet, key := writeWallet(t)

	cfg := Config{Enabled: true, RPCURL: server.URL + "/devnet?api-key=secret", WalletPath: wallet, ConfirmTimeout: 5 * time.Second}
	tracePath, trace, err := Anchor(context.Background(), cfg, summaryPath, resultPath)
	if err != nil {
		t.Fatal(err)
	}
	if trace.Status != StatusAnchored || !trace.OK || len(trace.Signatures) != 1 || trace.Cluster != "devnet" {
		t.Fatalf("unexpected trace: %+v", trace)
	}
	if strings.Contains(trace.RPC, "secret") {
		t.Fatal("the RPC API key leaked into the trace")
	}
	checkMemoTransaction(t, rpc.sent, key.Public().(ed25519.PublicKey), trace.Memo)

	var written Trace
	data, _ := os.ReadFile(tracePath)
	if err := json.Unmarshal(data, &written); err != nil || written.MerkleRoot != trace.MerkleRoot {
		t.Fatalf("trace file not written: %v", err)
	}
	for _, task := range written.Tasks {
		if !VerifyProof(task.LeafHash, task.Proof, written.MerkleRoot) {
			t.Fatalf("task %s: stored proof does not verify", task.TaskID)
		}
		if leaf, _ := LeafHash(task.Task); leaf != task.LeafHash {
			t.Fatalf("task %s: stored leaf is not the hash of the stored task", task.TaskID)
		}
	}
}

func TestAnchorWithoutWalletKeepsTheTreeAndSaysWhy(t *testing.T) {
	summaryPath, resultPath := writeJobFiles(t)
	tracePath, trace, err := Anchor(context.Background(), Config{Enabled: true, RPCURL: "http://127.0.0.1:1"}, summaryPath, resultPath)
	if err == nil || trace.Status != StatusFailed || trace.MerkleRoot == "" || tracePath == "" {
		t.Fatalf("want a failed trace with its tree, got %+v (%v)", trace, err)
	}
	if !strings.Contains(trace.Error, "SILICIUM_SOLANA_WALLET") {
		t.Fatalf("error should name the missing setting: %s", trace.Error)
	}
}

func TestConfigFromEnv(t *testing.T) {
	t.Setenv("SILICIUM_DEVNET_TRACE", "1")
	t.Setenv("SILICIUM_SOLANA_RPC", "")
	t.Setenv("SILICIUM_DEVNET_CONFIRM_TIMEOUT_S", "7")
	cfg := ConfigFromEnv()
	if !cfg.Enabled || cfg.RPCURL != "https://api.devnet.solana.com" || cfg.ConfirmTimeout != 7*time.Second {
		t.Fatalf("unexpected config: %+v", cfg)
	}
	t.Setenv("SILICIUM_DEVNET_TRACE", "0")
	if ConfigFromEnv().Enabled {
		t.Fatal("0 must disable anchoring")
	}
}
