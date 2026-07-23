package handler

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestCompareSemanticVersions(t *testing.T) {
	tests := []struct {
		left, right string
		want        int
	}{
		{"0.2.9-dev.2", "0.2.9-dev.1", 1},
		{"0.2.9-dev.1", "0.2.9", -1},
		{"0.2.10", "0.2.9", 1},
		{"0.2.9", "0.2.9", 0},
	}
	for _, test := range tests {
		got := compareSemanticVersions(test.left, test.right)
		if got != test.want {
			t.Fatalf("compareSemanticVersions(%q, %q) = %d, want %d", test.left, test.right, got, test.want)
		}
	}
}

func TestLoadNetworkPeersAnnotatesOutdatedAndUnknownNodes(t *testing.T) {
	directory := t.TempDir()
	peersPath := filepath.Join(directory, "peers.json")
	manifestPath := filepath.Join(directory, "manifest.json")
	peers := map[string]any{"peers": []any{
		map[string]any{"node_id": "orchestrator-1"},
		map[string]any{"node_id": "old-worker", "app_version": "0.2.9-dev.0", "release_channel": "dev"},
		map[string]any{"node_id": "current-worker", "app_version": "0.2.9-dev.1", "release_channel": "dev", "release_build": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
		map[string]any{"node_id": "stale-build-worker", "app_version": "0.2.9-dev.1", "release_channel": "dev", "release_build": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
		map[string]any{"node_id": "legacy-worker"},
	}}
	manifest := map[string]any{"channels": map[string]any{
		"dev": map[string]any{"version": "0.2.9-dev.1", "build": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
	}}
	writeJSON := func(path string, value any) {
		raw, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, raw, 0o600); err != nil {
			t.Fatal(err)
		}
	}
	writeJSON(peersPath, peers)
	writeJSON(manifestPath, manifest)

	payload, err := loadNetworkPeers(peersPath, manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	annotated := payload["peers"].([]any)
	if annotated[0].(map[string]any)["outdated"].(bool) {
		t.Fatal("orchestrator must not be treated as a desktop release")
	}
	if !annotated[1].(map[string]any)["outdated"].(bool) {
		t.Fatal("older dev worker should be outdated")
	}
	if annotated[2].(map[string]any)["outdated"].(bool) {
		t.Fatal("latest dev worker should be current")
	}
	if !annotated[3].(map[string]any)["outdated"].(bool) {
		t.Fatal("same semantic version with another build should be outdated")
	}
	if annotated[3].(map[string]any)["version_status"] != "outdated-build" {
		t.Fatal("stale build should have an explicit status")
	}
	if !annotated[4].(map[string]any)["outdated"].(bool) {
		t.Fatal("legacy worker without telemetry should require an update")
	}
}
