package handler

import (
	"context"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

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
	LogicalCPUCount     int     `json:"logicalCpuCount"`
	SystemCPUPercent    float64 `json:"systemCpuPercent,omitempty"`
	SystemMemoryPercent float64 `json:"systemMemoryPercent,omitempty"`
	StorageUsedPercent  float64 `json:"storageUsedPercent,omitempty"`
	UpdatedAt           string  `json:"updatedAt,omitempty"`
}

type blockchainStatus struct {
	Status          string `json:"status"`
	Network         string `json:"network"`
	Configured      bool   `json:"configured"`
	ProgramID       string `json:"programId,omitempty"`
	TraceMode       string `json:"traceMode"`
	ProofReady      bool   `json:"proofReady"`
	ReadinessDetail string `json:"readinessDetail"`
}

type systemStatus struct {
	Status     string           `json:"status"`
	CheckedAt  time.Time        `json:"checkedAt"`
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

	value := h.buildSystemStatus(r.Context(), networkPeersFile(), networkManifestFile(), now)
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

func (h *Handler) buildSystemStatus(ctx context.Context, peersPath, manifestPath string, now time.Time) systemStatus {
	runnerConfig := silicium.ConfigFromEnv()
	proofReady, readinessDetail := silicium.CompactDevnetTraceReadiness(runnerConfig)
	blockchainState := "operational"
	if !proofReady {
		blockchainState = "degraded"
	}
	value := systemStatus{
		Status:    "operational",
		CheckedAt: now.UTC(),
		Backend:   componentStatus{Status: "operational", Database: "operational"},
		Network:   networkStatus{Status: "operational"},
		Blockchain: blockchainStatus{
			Status:          blockchainState,
			Network:         solanaNetwork(os.Getenv("SILICIUM_SOLANA_RPC")),
			Configured:      strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_RPC")) != "" && strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PROGRAM_ID")) != "",
			ProgramID:       strings.TrimSpace(os.Getenv("SILICIUM_SOLANA_PROGRAM_ID")),
			TraceMode:       runnerConfig.DevnetTraceMode,
			ProofReady:      proofReady,
			ReadinessDetail: readinessDetail,
		},
	}
	if blockchainState != "operational" {
		value.Status = "degraded"
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

	payload, err := loadNetworkPeers(peersPath, manifestPath)
	if err != nil {
		value.Network.Status = "unavailable"
		if value.Status == "operational" {
			value.Status = "degraded"
		}
	} else {
		peers, _ := payload["peers"].([]any)
		value.Network.Peers = len(peers)
		for _, raw := range peers {
			peer, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			status := strings.ToLower(stringField(peer, "status"))
			online, hasOnline := peer["online"].(bool)
			if status != "offline" && status != "disconnected" && (!hasOnline || online) {
				value.Network.ActivePeers++
			}
			if outdated, _ := peer["outdated"].(bool); outdated {
				value.Network.OutdatedPeers++
			}
		}
		if metrics, ok := payload["metrics"].(map[string]any); ok {
			value.Network.TelemetryNodes = int(networkInt64Value(metrics["telemetry_nodes"]))
			value.Network.ActiveTasks = int(networkInt64Value(metrics["active_tasks"]))
			value.Network.QueueDepth = int(networkInt64Value(metrics["queue_depth"]))
			value.Network.LogicalCPUCount = int(networkInt64Value(metrics["logical_cpu_count"]))
			if metric, ok := networkFloatValue(metrics["system_cpu_percent"]); ok {
				value.Network.SystemCPUPercent = metric
			}
			if metric, ok := networkFloatValue(metrics["system_memory_percent"]); ok {
				value.Network.SystemMemoryPercent = metric
			}
			if metric, ok := networkFloatValue(metrics["storage_used_percent"]); ok {
				value.Network.StorageUsedPercent = metric
			}
			value.Network.UpdatedAt = stringField(metrics, "updated_utc")
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
