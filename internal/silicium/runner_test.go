package silicium

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/silicium/internal/models"
)

func TestParseRaytracerSummaryFallsBackToPPMWhenPNGIsUnavailable(t *testing.T) {
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	payload := `{
		"success": true,
		"reassembled_png": "",
		"result_png_path": "",
		"result_path": "",
		"reassembled_ppm": "/tmp/render.ppm"
	}`
	if err := os.WriteFile(summaryPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	result := parseRaytracerSummary(summaryPath)

	if result.Status != "completed" {
		t.Fatalf("expected completed status, got %q", result.Status)
	}
	if result.ResultPath != "/tmp/render.ppm" {
		t.Fatalf("expected PPM fallback, got %q", result.ResultPath)
	}
}

func TestValidateRaytracerCompletionRejectsMissingArtifact(t *testing.T) {
	result := validateRaytracerCompletion(RunResult{Status: "completed"})
	if result.Status != "failed" || result.ErrorMessage != "raytracer_result_missing" {
		t.Fatalf("missing artifact must fail the job, got %#v", result)
	}
}

func TestValidateRaytracerCompletionAcceptsReadableArtifact(t *testing.T) {
	resultPath := filepath.Join(t.TempDir(), "render.png")
	if err := os.WriteFile(resultPath, []byte("png"), 0o600); err != nil {
		t.Fatal(err)
	}
	result := validateRaytracerCompletion(RunResult{Status: "completed", ResultPath: resultPath})
	if result.Status != "completed" || result.ErrorMessage != "" {
		t.Fatalf("readable artifact must complete the job, got %#v", result)
	}
}

func TestParseRaytracerSummaryReadsVerifiedBillingOnly(t *testing.T) {
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	payload := `{
		"success": true,
		"billing": {
			"schema": "silicium.verified-billing.v1",
			"billable_work_units": 12345,
			"receipt_set_hash": "receipt-set"
		}
	}`
	if err := os.WriteFile(summaryPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}

	result := parseRaytracerSummary(summaryPath)

	if result.BillableWorkUnits != 12345 {
		t.Fatalf("expected verified units, got %d", result.BillableWorkUnits)
	}
	if result.ComputeReceiptHash != "receipt-set" {
		t.Fatalf("expected receipt set hash, got %q", result.ComputeReceiptHash)
	}
}

func TestRunRaytracerSubmitsAndWaitsForRustNodeTask(t *testing.T) {
	networkRoot := t.TempDir()
	workloadRoot := t.TempDir()
	inputPath := filepath.Join(t.TempDir(), "scene.cfg")
	if err := os.WriteFile(inputPath, []byte("scene"), 0o600); err != nil {
		t.Fatal(err)
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/tasks":
			var submission ControlTaskSubmission
			if err := json.NewDecoder(r.Body).Decode(&submission); err != nil {
				t.Fatal(err)
			}
			if submission.RootJobID != "render-1" || submission.ScenePath != inputPath {
				t.Fatalf("unexpected task submission %#v", submission)
			}
			if err := os.MkdirAll(filepath.Dir(submission.OutputPath), 0o750); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(submission.OutputPath, []byte("P6\n1 1\n255\nRGB"), 0o600); err != nil {
				t.Fatal(err)
			}
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"task_id":"render-1","root_job_id":"render-1","status":"queued"}`))
		case r.Method == http.MethodGet && r.URL.Path == "/v1/tasks":
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"tasks":[{"task_id":"render-1","root_job_id":"render-1","status":"verified","result_hash":"hash"}]}`))
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.String())
		}
	}))
	defer server.Close()

	result := RunRaytracer(context.Background(), models.Job{
		SiliciumJobID: "render-1",
		InputPath:     inputPath,
	}, RunnerConfig{
		NetworkRoot:        networkRoot,
		WorkloadStorageDir: workloadRoot,
		NodeAPIURL:         server.URL,
	})
	if result.Status != "completed" || result.ComputeReceiptHash != "hash" || !regularResultFile(result.ResultPath) {
		t.Fatalf("unexpected Rust node run result %#v", result)
	}
}

func regularResultFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func TestPublishTaskControlCancelsThroughRustNodeAPI(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.URL.Path != "/v1/workloads/job-1/cancel" {
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer test-token" {
			t.Fatalf("unexpected authorization header %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"cancelled": 1}`))
	}))
	defer server.Close()

	err := PublishTaskControl(context.Background(), RunnerConfig{
		NodeAPIURL:       server.URL,
		NodeControlToken: "test-token",
	}, TaskControl{
		ControlID:  "control-1",
		RootJobID:  "job-1",
		Action:     "cancel",
		IssuerNode: "node-a",
	})
	if err != nil {
		t.Fatal(err)
	}
}
