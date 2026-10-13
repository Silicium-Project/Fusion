package handler

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestNetworkRootJobIDNormalizesNestedFragmentIDs(t *testing.T) {
	tests := []struct {
		name string
		item map[string]any
		want string
	}{
		{name: "top level root", item: map[string]any{"root_job_id": "site-render-1"}, want: "site-render-1"},
		{name: "nested root", item: map[string]any{"task": map[string]any{"root_job_id": "site-render-2"}}, want: "site-render-2"},
		{name: "fragment task fallback", item: map[string]any{"task_id": "site-render-3-frag-004-compute"}, want: "site-render-3"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := networkRootJobID(test.item); got != test.want {
				t.Fatalf("networkRootJobID(%#v) = %q, want %q", test.item, got, test.want)
			}
		})
	}
}

func TestNetworkTaskFailedCountsOnlyFailures(t *testing.T) {
	for _, status := range []string{"failed", "dead_lettered", "expired"} {
		if !networkTaskFailed(status) {
			t.Fatalf("%q must count as a failed task", status)
		}
	}
	if networkTaskFailed("cancelled") {
		t.Fatal("cancelled must not count as a failed task")
	}
}

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
	peersPath := filepath.Join(directory, "node.orchestrator-1.peers.json")
	manifestPath := filepath.Join(directory, "manifest.json")
	peers := map[string]any{"peers": []any{
		map[string]any{"node_id": "orchestrator-1", "self": true, "last_seen_unix": time.Now().Unix()},
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
	writeJSON(filepath.Join(directory, "node.orchestrator-1.heartbeat.json"), map[string]any{
		"node_id":       "orchestrator-1",
		"timestamp_utc": time.Now().UTC().Format(time.RFC3339),
		"telemetry":     map[string]any{"system_cpu_percent": 12.5, "system_memory_percent": 41.25, "storage_used_percent": 33.0, "logical_cpu_count": 8},
	})
	writeJSON(filepath.Join(directory, "node.orchestrator-1.metrics.json"), map[string]any{"handled": 4, "failed": 1, "updated_utc": time.Now().UTC().Format(time.RFC3339)})

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
	local := annotated[0].(map[string]any)
	if local["online"] != true || local["last_seen_utc"] == "" {
		t.Fatalf("local peer liveness was not annotated: %#v", local)
	}
	telemetry, ok := local["telemetry"].(map[string]any)
	if !ok || telemetry["system_cpu_percent"] != 12.5 {
		t.Fatalf("local peer telemetry was not loaded: %#v", local)
	}
	metrics, ok := payload["metrics"].(map[string]any)
	if !ok || metrics["telemetry_nodes"] != 1 || metrics["logical_cpu_count"] != 8 {
		t.Fatalf("network metrics were not aggregated: %#v", payload["metrics"])
	}
}
