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

func TestValidateWorkloadAcceptsTheNodeWorkloads(t *testing.T) {
	for _, workload := range []string{"", "raytracer", "calcul/integrity/sha256", "calcul/hash/sha256"} {
		if err := ValidateWorkload(workload); err != nil {
			t.Fatalf("%q refused: %v", workload, err)
		}
	}
	if ValidateWorkload("calcul/unknown") == nil {
		t.Fatal("unknown workload accepted")
	}
}

// A sha256 job is submitted under its node identifier and its result is the
// JSON the node writes under sha256/<job>/result/.
func TestRunJobSubmitsASha256Job(t *testing.T) {
	workloadRoot := t.TempDir()
	inputPath := filepath.Join(t.TempDir(), "payload.bin")
	if err := os.WriteFile(inputPath, []byte("abc"), 0o600); err != nil {
		t.Fatal(err)
	}
	resultPath := filepath.Join(workloadRoot, "sha256", "hash-1", "result", "sha256.json")

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/v1/tasks":
			var submission ControlTaskSubmission
			if err := json.NewDecoder(r.Body).Decode(&submission); err != nil {
				t.Fatal(err)
			}
			if submission.Workload != "calcul/integrity/sha256" || submission.OutputPath != resultPath {
				t.Fatalf("unexpected submission %#v", submission)
			}
			_, _ = w.Write([]byte(`{"task_id":"hash-1","root_job_id":"hash-1","status":"queued"}`))
		case r.Method == http.MethodGet && r.URL.Path == "/v1/tasks":
			// The node assembles the result once every chunk is finalized.
			if err := os.MkdirAll(filepath.Dir(resultPath), 0o750); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(resultPath, []byte(`{"chunk_count":1}`), 0o600); err != nil {
				t.Fatal(err)
			}
			_, _ = w.Write([]byte(`{"tasks":[{"task_id":"hash-1.f000","root_job_id":"hash-1","status":"completed","result_hash":"h"}]}`))
		default:
			t.Fatalf("unexpected request %s %s", r.Method, r.URL.String())
		}
	}))
	defer server.Close()

	result := RunJob(context.Background(), models.Job{
		SiliciumJobID: "hash-1",
		Workload:      "calcul/hash/sha256",
		InputPath:     inputPath,
	}, RunnerConfig{
		NetworkRoot:        t.TempDir(),
		WorkloadStorageDir: workloadRoot,
		NodeAPIURL:         server.URL,
	})
	if result.Status != "completed" || result.ResultPath != resultPath {
		t.Fatalf("unexpected result %#v", result)
	}
}

func TestRunJobRefusesAnUnknownWorkload(t *testing.T) {
	result := RunJob(context.Background(), models.Job{Workload: "calcul/unknown"}, RunnerConfig{})
	if result.Status != "failed" || result.ErrorMessage != "unsupported workload" {
		t.Fatalf("unexpected result %#v", result)
	}
}

func TestJobStorageDirFollowsTheNodeLayout(t *testing.T) {
	for workload, want := range map[string]string{"": "raytracer", "raytracer": "raytracer", "calcul/hash/sha256": "sha256"} {
		if got, ok := JobStorageDir(workload); !ok || got != want {
			t.Fatalf("JobStorageDir(%q) = %q, %v; want %q", workload, got, ok, want)
		}
	}
	if _, ok := JobStorageDir("calcul/unknown"); ok {
		t.Fatal("unknown workload has a storage directory")
	}
}

func TestViewableResultPathPrefersTheRenderPNG(t *testing.T) {
	jobDir := t.TempDir()
	ppm := filepath.Join(jobDir, "reassembled", "render.ppm")
	if err := os.MkdirAll(filepath.Dir(ppm), 0o750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(ppm, []byte("P6"), 0o600); err != nil {
		t.Fatal(err)
	}
	if got := ViewableResultPath("raytracer", ppm); got != ppm {
		t.Fatalf("without a PNG the PPM stays the result, got %s", got)
	}
	png := filepath.Join(jobDir, "reassembled", "render.png")
	if err := os.WriteFile(png, []byte("png"), 0o600); err != nil {
		t.Fatal(err)
	}
	if got := ViewableResultPath("raytracer", ppm); got != png {
		t.Fatalf("want the PNG, got %s", got)
	}
	if got := ViewableResultPath("", ppm); got != png {
		t.Fatalf("older jobs without a workload are renders too, got %s", got)
	}
	report := filepath.Join(jobDir, "result", "sha256.json")
	if got := ViewableResultPath("calcul/integrity/sha256", report); got != report {
		t.Fatalf("other workloads keep their result, got %s", got)
	}
}
