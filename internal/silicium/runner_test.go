package silicium

import (
	"os"
	"path/filepath"
	"testing"
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
