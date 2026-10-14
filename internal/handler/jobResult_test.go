package handler

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/silicium/internal/models"
)

func TestRenderResultIsServedAsPNGWithItsName(t *testing.T) {
	jobDir := t.TempDir()
	ppm := filepath.Join(jobDir, "reassembled", "render.ppm")
	png := filepath.Join(jobDir, "reassembled", "render.png")
	if err := os.MkdirAll(filepath.Dir(ppm), 0o750); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(ppm, []byte("P6\n1 1\n255\n\x00\x00\x00"), 0o600)
	_ = os.WriteFile(png, []byte("\x89PNG\r\n\x1a\n"), 0o600)

	response := httptest.NewRecorder()
	serveJobResult(response, httptest.NewRequest(http.MethodGet, "/jobs/1/result", nil), models.Job{Workload: "raytracer", ResultPath: ppm})
	if got := response.Header().Get("Content-Type"); got != "image/png" {
		t.Fatalf("a render must be served as its PNG, got %q", got)
	}
	if got := response.Header().Get("Content-Disposition"); got != `inline; filename="result.png"` {
		t.Fatalf("unexpected file name: %q", got)
	}

	_ = os.Remove(png)
	response = httptest.NewRecorder()
	serveJobResult(response, httptest.NewRequest(http.MethodGet, "/jobs/1/result", nil), models.Job{Workload: "raytracer", ResultPath: ppm})
	if got := response.Header().Get("Content-Type"); got != "image/x-portable-pixmap" {
		t.Fatalf("without a PNG the PPM keeps its type, got %q", got)
	}
}
