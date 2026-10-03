package handler

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestSystemStatusAggregatesPeersAndConfiguration(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/peers" {
			t.Fatalf("unexpected path %q", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"peers":[{"node_id":"node-a","online":true},{"node_id":"node-b","online":true},{"node_id":"node-c","online":false}],"metrics":{"active_tasks":1,"known_tasks":2}}`))
	}))
	defer server.Close()
	t.Setenv("SILICIUM_NODE_API_URL", server.URL)
	t.Setenv("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com")
	t.Setenv("SILICIUM_SOLANA_PROGRAM_ID", "program-id")

	value := (&Handler{}).buildSystemStatus(context.Background(), time.Now())
	if value.Network.Peers != 3 || value.Network.ActivePeers != 2 || value.Network.ActiveTasks != 1 || value.Network.QueueDepth != 2 {
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

func TestSolanaNetworkIsUnknownWhenRPCIsNotConfigured(t *testing.T) {
	if got := solanaNetwork(""); got != "unknown" {
		t.Fatalf("expected unknown network without an RPC, got %q", got)
	}
}
