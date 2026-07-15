package silicium

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestConfiguredDevnetTraceMode(t *testing.T) {
	tests := []struct {
		name     string
		mode     string
		legacy   string
		expected string
	}{
		{name: "default compact", expected: "async_compact"},
		{name: "explicit compact", mode: "async_compact", legacy: "0", expected: "async_compact"},
		{name: "compact alias", mode: "compact", expected: "async_compact"},
		{name: "full demo", mode: "full_demo", expected: "full_demo"},
		{name: "legacy enabled", legacy: "1", expected: "full_demo"},
		{name: "legacy disabled", legacy: "0", expected: "off"},
		{name: "invalid mode is safe", mode: "unknown", expected: "off"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Setenv("SILICIUM_DEVNET_TRACE_MODE", test.mode)
			t.Setenv("SILICIUM_DEVNET_TRACE", test.legacy)
			if actual := configuredDevnetTraceMode(); actual != test.expected {
				t.Fatalf("configuredDevnetTraceMode() = %q, want %q", actual, test.expected)
			}
		})
	}
}

func TestPrepareCompactDevnetTrace(t *testing.T) {
	summaryPath := filepath.Join(t.TempDir(), "raytracer-summary.json")
	if err := os.WriteFile(summaryPath, []byte(`{"success":true}`), 0o644); err != nil {
		t.Fatal(err)
	}

	tracePath, err := PrepareCompactDevnetTrace(summaryPath)
	if err != nil {
		t.Fatal(err)
	}
	if tracePath != filepath.Join(filepath.Dir(summaryPath), "devnet-compact-trace.json") {
		t.Fatalf("unexpected trace path %q", tracePath)
	}

	data, err := os.ReadFile(tracePath)
	if err != nil {
		t.Fatal(err)
	}
	var trace map[string]any
	if err := json.Unmarshal(data, &trace); err != nil {
		t.Fatal(err)
	}
	if trace["mode"] != "async_compact" || trace["status"] != "pending" || trace["enabled"] != true {
		t.Fatalf("unexpected pending trace: %#v", trace)
	}
}
