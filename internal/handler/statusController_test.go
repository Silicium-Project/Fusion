package handler

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestSystemStatusAggregatesPeersAndConfiguration(t *testing.T) {
	directory := t.TempDir()
	peersPath := filepath.Join(directory, "peers.json")
	manifestPath := filepath.Join(directory, "manifest.json")
	writeStatusFixture(t, peersPath, map[string]any{"peers": []any{
		map[string]any{"node_id": "orchestrator-1", "online": true},
		map[string]any{"node_id": "worker-current", "online": true, "app_version": "1.0.0", "release_channel": "prod", "release_build": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
		map[string]any{"node_id": "worker-old", "online": false, "app_version": "0.9.0", "release_channel": "prod"},
	}})
	writeStatusFixture(t, manifestPath, map[string]any{"channels": map[string]any{
		"prod": map[string]any{"version": "1.0.0", "build": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
	}})
	t.Setenv("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com")
	t.Setenv("SILICIUM_SOLANA_PROGRAM_ID", "program-id")

	value := (&Handler{}).buildSystemStatus(context.Background(), peersPath, manifestPath, time.Now())
	if value.Network.Peers != 3 || value.Network.ActivePeers != 2 || value.Network.OutdatedPeers != 1 {
		t.Fatalf("unexpected peer summary: %#v", value.Network)
	}
	if !value.Blockchain.Configured || value.Blockchain.Network != "devnet" {
		t.Fatalf("unexpected blockchain summary: %#v", value.Blockchain)
	}
	if value.Status != "unavailable" || value.Backend.Database != "unavailable" {
		t.Fatalf("nil database should keep the endpoint available but report backend unavailable: %#v", value)
	}
}

func TestStatusCacheExpires(t *testing.T) {
	cache := &statusCache{}
	now := time.Now()
	want := systemStatus{Status: "operational"}
	cache.put(want, now)
	if got, ok := cache.get(now.Add(time.Second)); !ok || got.Status != want.Status {
		t.Fatal("fresh cache entry was missed")
	}
	if _, ok := cache.get(now.Add(statusCacheLifetime)); ok {
		t.Fatal("expired cache entry was returned")
	}
}

func writeStatusFixture(t *testing.T, path string, value any) {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
}
