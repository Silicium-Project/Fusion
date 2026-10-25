package silicium

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// The node writes the image a moment after the fragments are finalized.
func TestWaitForReassembledImageWaitsForTheNode(t *testing.T) {
	dir := t.TempDir()
	resultPath := filepath.Join(dir, "reassembled", "render.ppm")
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	go func() {
		time.Sleep(700 * time.Millisecond)
		_ = os.MkdirAll(filepath.Dir(resultPath), 0o750)
		_ = os.WriteFile(resultPath, []byte("P6"), 0o600)
	}()
	if err := waitForReassembledImage(context.Background(), resultPath, summaryPath, 5*time.Second); err != nil {
		t.Fatalf("expected the image to be awaited, got %v", err)
	}
}

func TestWaitForReassembledImageReportsTheNodeFailure(t *testing.T) {
	dir := t.TempDir()
	summaryPath := filepath.Join(dir, "raytracer-summary.json")
	payload := `{"success": false, "error": "rust_node_fragment_failed"}`
	if err := os.WriteFile(summaryPath, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}
	err := waitForReassembledImage(context.Background(), filepath.Join(dir, "render.ppm"), summaryPath, 5*time.Second)
	if err == nil || err.Error() != "rust_node_fragment_failed" {
		t.Fatalf("expected the node error, got %v", err)
	}
}

func TestWaitForReassembledImageTimesOut(t *testing.T) {
	dir := t.TempDir()
	err := waitForReassembledImage(context.Background(), filepath.Join(dir, "render.ppm"),
		filepath.Join(dir, "raytracer-summary.json"), 600*time.Millisecond)
	if err == nil || !strings.HasPrefix(err.Error(), "raytracer_result_timeout") {
		t.Fatalf("expected a timeout, got %v", err)
	}
}
