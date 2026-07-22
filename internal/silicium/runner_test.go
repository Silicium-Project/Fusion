package silicium

import (
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
