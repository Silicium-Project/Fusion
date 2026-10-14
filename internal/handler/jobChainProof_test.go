package handler

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/silicium/internal/chainproof"
	"github.com/silicium/internal/models"
	"gorm.io/gorm"
)

// fakeSolanaRPC confirms every memo transaction it receives.
func fakeSolanaRPC(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var request struct {
			Method string            `json:"method"`
			Params []json.RawMessage `json:"params"`
		}
		_ = json.Unmarshal(body, &request)
		switch request.Method {
		case "getLatestBlockhash":
			fmt.Fprintf(w, `{"result":{"value":{"blockhash":%q}}}`, chainproof.MemoProgramID)
		case "sendTransaction":
			var encoded string
			_ = json.Unmarshal(request.Params[0], &encoded)
			wire, _ := base64.StdEncoding.DecodeString(encoded)
			fmt.Fprintf(w, `{"result":%q}`, chainproof.Base58Encode(wire[1:65]))
		default:
			fmt.Fprint(w, `{"result":{"value":[{"confirmationStatus":"finalized","err":null}]}}`)
		}
	}))
}

func writeTestWallet(t *testing.T) string {
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
	return path
}

func TestCompletedJobIsAnchoredAndShownOnTheDashboard(t *testing.T) {
	database, err := gorm.Open(sqlite.Open("file:anchor-job?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := database.AutoMigrate(&models.Job{}); err != nil {
		t.Fatal(err)
	}
	sqlDB, _ := database.DB()
	defer sqlDB.Close()
	sqlDB.SetMaxOpenConns(1)

	jobDir := t.TempDir()
	summaryPath := filepath.Join(jobDir, "raytracer-summary.json")
	resultPath := filepath.Join(jobDir, "render.png")
	summary := `{"job_id":"site-render-1-1","workload":"raytracer","fragments":[
	  {"fragment_index":0,"task_id":"a.f000","status":"completed","result_hash":"r0",
	   "trace":{"worker":"w0","claim_event":"c0","result_event":"e0","result_sha256":"r0",
	            "verifiers":[{"author":"v0","verdict":true,"verification_event":"x0","self_verification":false}]}},
	  {"fragment_index":1,"task_id":"a.f001","status":"completed","result_hash":"r1","worker":"w1"}]}`
	if err := os.WriteFile(summaryPath, []byte(summary), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(resultPath, []byte("png"), 0o600); err != nil {
		t.Fatal(err)
	}
	job := models.Job{UserID: 1, Title: "t", Workload: "raytracer", Status: "completed",
		SiliciumJobID: "site-render-1-1", InputPath: "scene", SummaryPath: summaryPath, ResultPath: resultPath}
	if err := database.Create(&job).Error; err != nil {
		t.Fatal(err)
	}

	server := fakeSolanaRPC(t)
	defer server.Close()
	t.Setenv("SILICIUM_DEVNET_TRACE", "1")
	t.Setenv("SILICIUM_SOLANA_RPC", server.URL+"/devnet")
	t.Setenv("SILICIUM_SOLANA_WALLET", writeTestWallet(t))

	(&Handler{DB: database}).anchorJobOnChain(job.ID)

	var stored models.Job
	database.First(&stored, job.ID)
	if stored.DevnetTracePath != filepath.Join(jobDir, chainproof.TraceFileName) || stored.DevnetJob == "" {
		t.Fatalf("trace not recorded on the job: %+v", stored)
	}
	view := devnetDashboard(stored, map[string]any{})
	if view["status"] != chainproof.StatusAnchored || view["ok"] != true {
		t.Fatalf("unexpected dashboard block: %+v", view)
	}
	signatures, _ := view["signatures"].([]any)
	if len(signatures) != 1 || signatures[0] != stored.DevnetJob {
		t.Fatalf("dashboard does not show the transaction: %+v", view["signatures"])
	}
	tasks, _ := view["fragments"].([]any)
	if len(tasks) != 2 {
		t.Fatalf("dashboard does not list the anchored tasks: %+v", view["fragments"])
	}
	first, _ := tasks[0].(map[string]any)
	if first["worker"] != "w0" || first["leaf_hash"] == "" {
		t.Fatalf("task trace incomplete: %+v", first)
	}
}

func TestDashboardSaysWhenNoTraceIsExpected(t *testing.T) {
	t.Setenv("SILICIUM_DEVNET_TRACE", "0")
	if view := devnetDashboard(models.Job{Status: "completed"}, map[string]any{}); view["status"] != "not_requested" || view["enabled"] != false {
		t.Fatalf("disabled anchoring must read not_requested: %+v", view)
	}
	t.Setenv("SILICIUM_DEVNET_TRACE", "1")
	if view := devnetDashboard(models.Job{Status: "completed"}, map[string]any{}); view["status"] != chainproof.StatusPending {
		t.Fatalf("a completed job waiting for its anchor must read pending: %+v", view)
	}
	if view := devnetDashboard(models.Job{Status: "running"}, map[string]any{}); view["status"] != "not_requested" {
		t.Fatalf("a running job has no trace yet: %+v", view)
	}
}

func TestAnchoringIsSkippedWhenDisabled(t *testing.T) {
	t.Setenv("SILICIUM_DEVNET_TRACE", "0")
	// No database: the call must return before touching it.
	(&Handler{}).anchorJobOnChain(1)
}
