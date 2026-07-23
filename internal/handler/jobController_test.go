package handler

import (
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

func TestBoundedQueryInt(t *testing.T) {
	request := httptest.NewRequest("GET", "/jobs?page=900&page_size=0", nil)
	if page := boundedQueryInt(request, "page", 1, 1, 100); page != 100 {
		t.Fatalf("expected upper bound, got %d", page)
	}
	if pageSize := boundedQueryInt(request, "page_size", 20, 1, 100); pageSize != 1 {
		t.Fatalf("expected lower bound, got %d", pageSize)
	}
	if fallback := boundedQueryInt(request, "missing", 20, 1, 100); fallback != 20 {
		t.Fatalf("expected fallback, got %d", fallback)
	}
}

func TestVerifiedBillingForCancelledJobOnlyCountsCosignedFragments(t *testing.T) {
	progressPath := filepath.Join(t.TempDir(), "raytracer-progress.json")
	payload := `{"fragments":[
		{"compute_billable_work_units":100,"verify_billable_work_units":10,
		 "compute_receipt_hash":"compute-a","verify_receipt_hash":"verify-a",
		 "receipt_attestation":{"accepted":true}},
		{"compute_billable_work_units":999,"verify_billable_work_units":999,
		 "compute_receipt_hash":"forged","receipt_attestation":{"accepted":false}}
	]}`
	if err := os.WriteFile(progressPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}
	units, receiptHash := verifiedBillingForJob(models.Job{
		Workload:    "raytracer",
		SummaryPath: filepath.Join(filepath.Dir(progressPath), "summary.json"),
	})
	if units != 110 {
		t.Fatalf("expected 110 verified units, got %d", units)
	}
	if receiptHash == "" {
		t.Fatal("expected a receipt-set hash")
	}
}

func TestActiveTaskRootIDsOnlyReturnsNonTerminalDescendants(t *testing.T) {
	exportDir := t.TempDir()
	tasksDir := filepath.Join(exportDir, "tasks")
	if err := os.MkdirAll(tasksDir, 0o755); err != nil {
		t.Fatal(err)
	}
	envelopes := map[string]map[string]any{
		"active.json": {
			"task_id": "site-render-1-frag-004-compute-retry-02",
			"status":  "dispatched",
		},
		"nested.json": {
			"task_id": "custom-task",
			"status":  "running",
			"task":    map[string]any{"root_job_id": "site-render-2"},
		},
		"done.json": {
			"task_id":     "site-render-3-frag-001",
			"root_job_id": "site-render-3",
			"status":      "completed",
		},
	}
	for name, envelope := range envelopes {
		raw, err := json.Marshal(envelope)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(tasksDir, name), raw, 0o600); err != nil {
			t.Fatal(err)
		}
	}

	roots, err := activeTaskRootIDs(exportDir)
	if err != nil {
		t.Fatal(err)
	}
	if !roots["site-render-1"] || !roots["site-render-2"] || roots["site-render-3"] || len(roots) != 2 {
		t.Fatalf("unexpected active roots: %#v", roots)
	}
}

func TestTerminalTaskControlIsStableAndRecursive(t *testing.T) {
	deadline := time.Date(2026, 7, 24, 1, 2, 3, 0, time.UTC)
	job := models.Job{SiliciumJobID: "site-render-9", DeadlineAt: &deadline}
	cfg := silicium.RunnerConfig{OrchestratorNodeID: "orchestrator-1"}

	failed := terminalTaskControl(job, "failed", "worker failed", deadline, cfg)
	if failed.ControlID != "site-render-9-cancel-terminal" || failed.RootJobID != job.SiliciumJobID || failed.Action != "cancel" {
		t.Fatalf("unexpected failed control: %#v", failed)
	}
	expired := terminalTaskControl(job, "expired", "deadline", deadline, cfg)
	if expired.ControlID != "site-render-9-expire-terminal" || expired.Action != "expire" || expired.DeadlineUTC == "" {
		t.Fatalf("unexpected expiry control: %#v", expired)
	}
}
