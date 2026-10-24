package handler

import (
	"context"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/silicium/internal/release"
	"github.com/silicium/internal/silicium"
)

const statusCacheLifetime = 5 * time.Second

type componentStatus struct {
	Status   string `json:"status"`
	Database string `json:"database,omitempty"`
}

type networkStatus struct {
	Status              string  `json:"status"`
	Peers               int     `json:"peers"`
	ActivePeers         int     `json:"activePeers"`
	OutdatedPeers       int     `json:"outdatedPeers"`
	TelemetryNodes      int     `json:"telemetryNodes"`
	ActiveTasks         int     `json:"activeTasks"`
	QueueDepth          int     `json:"queueDepth"`
	KnownTasks          int     `json:"knownTasks"`
	LogicalCPUCount     int     `json:"logicalCpuCount"`
	SystemCPUPercent    float64 `json:"systemCpuPercent,omitempty"`
	SystemMemoryPercent float64 `json:"systemMemoryPercent,omitempty"`
	StorageUsedPercent  float64 `json:"storageUsedPercent,omitempty"`
	UpdatedAt           string  `json:"updatedAt,omitempty"`
}

type blockchainStatus struct {
	Status     string `json:"status"`
	Network    string `json:"network"`
	Configured bool   `json:"configured"`
	ProgramID  string `json:"programId,omitempty"`
}

type systemStatus struct {
	Status     string           `json:"status"`
	CheckedAt  time.Time        `json:"checkedAt"`
	Release    release.Metadata `json:"release"`
	Backend    componentStatus  `json:"backend"`
	Network    networkStatus    `json:"network"`
	Blockchain blockchainStatus `json:"blockchain"`
}

type statusCache struct {
	mu        sync.Mutex
	value     systemStatus
	expiresAt time.Time
}

func (c *statusCache) get(now time.Time) (systemStatus, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.value, !c.expiresAt.IsZero() && c.expiresAt.After(now)
}

func (c *statusCache) put(value systemStatus, now time.Time) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.value = value
	c.expiresAt = now.Add(statusCacheLifetime)
}

func (h *Handler) GetStatus(w http.ResponseWriter, r *http.Request) {
	now := time.Now().UTC()
	if h.status != nil {
		if cached, ok := h.status.get(now); ok {
			w.Header().Set("X-Silicium-Cache", "hit")
			writeStatus(w, cached)
			return
		}
	}

	value := h.buildSystemStatus(r.Context(), now)
	if h.status != nil {
		h.status.put(value, now)
	}
	w.Header().Set("X-Silicium-Cache", "miss")
	writeStatus(w, value)
}

func writeStatus(w http.ResponseWriter, value systemStatus) {
	w.Header().Set("Cache-Control", "public, max-age=5, stale-while-revalidate=25")
	writeJSON(w, http.StatusOK, value)
}

func (h *Handler) buildSystemStatus(ctx context.Context, now time.Time) systemStatus {
	value := systemStatus{
		Status:    "operational",
		CheckedAt: now.UTC(),
		Release:   release.Current(),
		Backend:   componentStatus{Status: "operational", Database: "operational"},
		Network:   networkStatus{Status: "operational"},
		Blockchain: blockchainStatus{
			Status:     "operational",
			Network:    solanaNetwork(os.Getenv("SILICIUM_SOLANA_RPC")),
			Configured: strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_RPC")) != "" && strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PROGRAM_ID")) != "",
			ProgramID:  strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PROGRAM_ID")),
		},
	}

	if h.DB == nil {
		value.Backend.Status = "unavailable"
		value.Backend.Database = "unavailable"
		value.Status = "unavailable"
	} else if sqlDB, err := h.DB.DB(); err != nil || pingDatabase(ctx, sqlDB) != nil {
		value.Backend.Status = "degraded"
		value.Backend.Database = "unavailable"
		value.Status = "degraded"
	}

	payload, err := silicium.ListControlPeers(ctx, silicium.ConfigFromEnv())
	if err != nil {
		value.Network.Status = "unavailable"
		if value.Status == "operational" {
			value.Status = "degraded"
		}
	} else {
		peers, _ := payload["peers"].([]map[string]any)
		value.Network.Peers = len(peers)
		for _, peer := range peers {
			status := strings.ToLower(stringField(peer, "status"))
			online, hasOnline := peer["online"].(bool)
			if status != "offline" && status != "disconnected" && (!hasOnline || online) {
				value.Network.ActivePeers++
			}
		}
		if metrics, ok := payload["metrics"].(map[string]any); ok {
			value.Network.TelemetryNodes = value.Network.Peers
			value.Network.ActiveTasks = int(networkInt64Value(metrics["active_tasks"]))
			value.Network.QueueDepth = int(networkInt64Value(metrics["queue_depth"]))
			value.Network.KnownTasks = int(networkInt64Value(metrics["known_tasks"]))
			value.Network.UpdatedAt = now.UTC().Format(time.RFC3339)
		}
		if value.Network.Peers == 0 || value.Network.ActivePeers == 0 {
			value.Network.Status = "degraded"
			if value.Status == "operational" {
				value.Status = "degraded"
			}
		}
	}

	if !value.Blockchain.Configured {
		value.Blockchain.Status = "degraded"
		if value.Status == "operational" {
			value.Status = "degraded"
		}
	}
	return value
}

type databasePinger interface {
	PingContext(context.Context) error
}

func pingDatabase(parent context.Context, database databasePinger) error {
	ctx, cancel := context.WithTimeout(parent, 800*time.Millisecond)
	defer cancel()
	return database.PingContext(ctx)
}

func solanaNetwork(rpc string) string {
	value := strings.ToLower(strings.TrimSpace(rpc))
	switch {
	case value == "":
		return "unknown"
	case strings.Contains(value, "mainnet"):
		return "mainnet"
	case strings.Contains(value, "testnet"):
		return "testnet"
	default:
		return "devnet"
	}
}
