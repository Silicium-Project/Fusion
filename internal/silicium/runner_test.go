package silicium

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
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

func TestRaytracerArgsForwardRequestedFragmentCount(t *testing.T) {
	args := raytracerArgs(
		models.Job{InputPath: "/tmp/scene.cfg", SiliciumJobID: "render-1", FragmentCount: 73},
		RunnerConfig{},
	)

	index := slices.Index(args, "--fragments")
	if index < 0 || index+1 >= len(args) || args[index+1] != "73" {
		t.Fatalf("expected --fragments 73, got %#v", args)
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

func TestPublishTaskControlUsesMeshAuthentication(t *testing.T) {
	var received map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer mesh-secret" {
			t.Fatalf("unexpected authorization %q", got)
		}
		if err := json.NewDecoder(r.Body).Decode(&received); err != nil {
			t.Fatal(err)
		}
		w.WriteHeader(http.StatusAccepted)
	}))
	defer server.Close()

	err := PublishTaskControl(context.Background(), RunnerConfig{
		ControlURL: server.URL,
		MeshKey:    "mesh-secret",
	}, TaskControl{
		ControlID:  "control-1",
		RootJobID:  "job-1",
		Action:     "cancel",
		IssuerNode: "node-a",
	})
	if err != nil {
		t.Fatal(err)
	}
	if received["topic"] != "task_control" {
		t.Fatalf("unexpected topic %#v", received["topic"])
	}
}
