package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/silicium/internal/contextkeys"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
	"github.com/glebarez/sqlite"
	"gorm.io/gorm"
)

func TestCreateJobStoresUploadedRaytracerScene(t *testing.T) {
	database, err := gorm.Open(sqlite.Open("file:create-job?mode=memory&cache=shared"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := database.AutoMigrate(&models.Job{}); err != nil {
		t.Fatal(err)
	}
	sqlDB, err := database.DB()
	if err != nil {
		t.Fatal(err)
	}
	defer sqlDB.Close()
	sqlDB.SetMaxOpenConns(1)

	storage := t.TempDir()
	t.Setenv("SILICIUM_SITE_STORAGE_DIR", storage)
	scene := []byte(`# Silicium raytracer fixture
camera :
{
	resolution = { width = 32 height = 20 }
	position = { x = 0 y = 0 z = 0 }
}
`)
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for key, value := range map[string]string{
		"title":               "File-backed render",
		"workload":            "raytracer",
		"priority":            "normal",
		"fragment_count":      "1",
		"max_runtime_seconds": "60",
	} {
		if err := form.WriteField(key, value); err != nil {
			t.Fatal(err)
		}
	}
	part, err := form.CreateFormFile("file", `C:\fixtures\demo-scene.cfg`)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := part.Write(scene); err != nil {
		t.Fatal(err)
	}
	if err := form.Close(); err != nil {
		t.Fatal(err)
	}

	request := httptest.NewRequest(http.MethodPost, "/jobs", &body)
	request.Header.Set("Content-Type", form.FormDataContentType())
	request = request.WithContext(context.WithValue(request.Context(), contextkeys.UserIDKey, "42"))
	h := New(database)
	started := make(chan uint, 1)
	h.jobRunner = func(jobID uint) { started <- jobID }
	response := httptest.NewRecorder()
	h.CreateJob(response, request)

	if response.Code != http.StatusAccepted {
		t.Fatalf("CreateJob status = %d, body = %s", response.Code, response.Body.String())
	}
	var job models.Job
	if result := database.First(&job); result.Error != nil {
		t.Fatal(result.Error)
	}
	if job.UserID != 42 || job.Workload != "raytracer" || job.Status != "queued" {
		t.Fatalf("unexpected stored job: %#v", job)
	}
	stored, err := os.ReadFile(job.InputPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(stored, scene) {
		t.Fatalf("stored scene differs from upload: got %q", stored)
	}
	if filepath.Base(job.InputPath) != "demo-scene.cfg" {
		t.Fatalf("unsafe or unexpected stored filename: %q", job.InputPath)
	}
	select {
	case jobID := <-started:
		if jobID != job.ID {
			t.Fatalf("started job id = %d, want %d", jobID, job.ID)
		}
	case <-time.After(time.Second):
		t.Fatal("job runner was not scheduled")
	}
	var payload map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if _, exposed := payload["inputPath"]; exposed {
		t.Fatal("response must not expose the server-side input path")
	}
}

func TestStoreJobInputRejectsEmptyFiles(t *testing.T) {
	_, err := storeJobInput(t.TempDir(), "empty.cfg", bytes.NewReader(nil))
	if err == nil || !errors.Is(err, errEmptyJobInput) {
		t.Fatalf("expected empty input error, got %v", err)
	}
}

func TestStoreJobInputRejectsOversizedFiles(t *testing.T) {
	oversized := bytes.Repeat([]byte{'x'}, int(maxJobInputBytes+1))
	_, err := storeJobInput(t.TempDir(), "oversized.cfg", bytes.NewReader(oversized))
	if err == nil || !errors.Is(err, errJobInputTooLarge) {
		t.Fatalf("expected oversized input error, got %v", err)
	}
}

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
