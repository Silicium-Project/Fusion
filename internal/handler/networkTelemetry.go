package handler

import (
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode"
)

const defaultNetworkPeerStaleAfterSeconds int64 = 300

var networkMetricCounters = []string{
	"handled",
	"failed",
	"retried",
	"dead_lettered",
	"dispatched",
	"dispatch_failed",
}

// enrichNetworkPeers keeps the peer registry as the source of identity and
// routing data, then joins the durable local heartbeat/metrics files when they
// are available. Remote peers carry the same runtime snapshot in activity.
// This makes the API explicit about what is observed instead of making the
// frontend infer liveness or invent resource values.
func enrichNetworkPeers(payload map[string]any, peersPath string) {
	peers, _ := payload["peers"].([]any)
	exportDir := filepath.Dir(peersPath)
	now := time.Now().UTC()
	for _, raw := range peers {
		peer, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		enrichNetworkPeer(peer, exportDir, now)
	}
	payload["metrics"] = aggregateNetworkMetrics(peers)
}

func enrichNetworkPeer(peer map[string]any, exportDir string, now time.Time) {
	nodeID := stringField(peer, "node_id")
	pathID := networkNodePathID(nodeID)
	heartbeat := map[string]any{}
	metricsFile := map[string]any{}
	if pathID != "" {
		heartbeat = readJSONMap(filepath.Join(exportDir, "node."+pathID+".heartbeat.json"))
		metricsFile = readJSONMap(filepath.Join(exportDir, "node."+pathID+".metrics.json"))
	}

	// A local heartbeat is authoritative for the local node. For remote nodes,
	// the signed peer announcement already contains activity.telemetry.
	mergeNetworkPeerField(peer, heartbeat, "roles")
	mergeNetworkPeerField(peer, heartbeat, "app_version")
	mergeNetworkPeerField(peer, heartbeat, "release_channel")
	mergeNetworkPeerField(peer, heartbeat, "release_build")
	mergeNetworkPeerField(peer, heartbeat, "capacity")
	mergeNetworkPeerField(peer, heartbeat, "activity")
	mergeNetworkPeerField(peer, heartbeat, "task_queue")

	runtime := networkPeerRuntime(peer)
	if len(runtime) == 0 {
		runtime = mapField(heartbeat, "telemetry")
	}
	if len(runtime) == 0 {
		runtime = mapField(metricsFile, "runtime")
	}
	if len(runtime) > 0 {
		peer["telemetry"] = runtime
	}

	peerMetrics := mapField(peer, "metrics")
	if peerMetrics == nil {
		peerMetrics = map[string]any{}
	}
	for _, key := range networkMetricCounters {
		if value, ok := metricsFile[key]; ok {
			peerMetrics[key] = value
		}
	}
	if len(runtime) > 0 {
		peerMetrics["runtime"] = runtime
	}
	if updated := firstNetworkTimestamp(metricsFile, heartbeat, peer); !updated.IsZero() {
		peer["telemetry_updated_utc"] = updated.Format(time.RFC3339Nano)
		peerMetrics["updated_utc"] = updated.Format(time.RFC3339Nano)
	}
	if len(peerMetrics) > 0 {
		peer["metrics"] = peerMetrics
	}

	lastSeenUnix := networkInt64Value(peer["last_seen_unix"])
	if lastSeenUnix == 0 {
		if timestamp := firstNetworkTimestamp(peer, heartbeat); !timestamp.IsZero() {
			lastSeenUnix = timestamp.Unix()
			peer["last_seen_unix"] = lastSeenUnix
		}
	}
	if lastSeenUnix > 0 {
		peer["last_seen_utc"] = time.Unix(lastSeenUnix, 0).UTC().Format(time.RFC3339)
		peer["online"] = now.Unix()-lastSeenUnix <= networkPeerStaleAfterSeconds()
	} else if _, exists := peer["online"]; !exists {
		// Missing heartbeat data is not evidence of an online machine.
		peer["online"] = false
	}
	if online, ok := peer["online"].(bool); ok {
		peer["availability_status"] = "offline"
		if online {
			peer["availability_status"] = "online"
		}
	}
}

func mergeNetworkPeerField(target, source map[string]any, key string) {
	if _, exists := target[key]; exists {
		return
	}
	if value, exists := source[key]; exists {
		target[key] = value
	}
}

func networkPeerRuntime(peer map[string]any) map[string]any {
	if runtime := mapField(peer, "telemetry"); len(runtime) > 0 {
		return runtime
	}
	if metrics := mapField(peer, "metrics"); len(metrics) > 0 {
		if runtime := mapField(metrics, "runtime"); len(runtime) > 0 {
			return runtime
		}
	}
	if activity := mapField(peer, "activity"); len(activity) > 0 {
		return mapField(activity, "telemetry")
	}
	return nil
}

func mapField(values map[string]any, key string) map[string]any {
	if values == nil {
		return nil
	}
	value, _ := values[key].(map[string]any)
	return value
}

func firstNetworkTimestamp(values ...map[string]any) time.Time {
	var latest time.Time
	for _, fields := range values {
		for _, key := range []string{"updated_utc", "timestamp_utc", "telemetry_updated_utc"} {
			value, ok := fields[key].(string)
			if !ok {
				continue
			}
			parsed, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(value))
			if err == nil && parsed.After(latest) {
				latest = parsed
			}
		}
	}
	return latest
}

func networkNodePathID(value string) string {
	var builder strings.Builder
	for _, character := range strings.TrimSpace(value) {
		if unicode.IsLetter(character) || unicode.IsDigit(character) || strings.ContainsRune("_.-", character) {
			builder.WriteRune(character)
			continue
		}
		builder.WriteByte('_')
	}
	return builder.String()
}

func networkPeerStaleAfterSeconds() int64 {
	value, err := strconv.ParseInt(strings.TrimSpace(os.Getenv("SILICIUM_PEER_STALE_AFTER_S")), 10, 64)
	if err != nil || value <= 0 {
		return defaultNetworkPeerStaleAfterSeconds
	}
	return value
}

func networkInt64Value(value any) int64 {
	switch parsed := value.(type) {
	case int:
		return int64(parsed)
	case int64:
		return parsed
	case float64:
		return int64(parsed)
	case float32:
		return int64(parsed)
	case jsonNumber:
		result, _ := strconv.ParseInt(string(parsed), 10, 64)
		return result
	default:
		return 0
	}
}

// jsonNumber is intentionally kept local to avoid changing the generic JSON
// decoding used by the handlers. It also makes this helper safe for tests that
// construct maps with integer values directly.
type jsonNumber string

func networkFloatValue(value any) (float64, bool) {
	switch parsed := value.(type) {
	case int:
		return float64(parsed), true
	case int64:
		return float64(parsed), true
	case float64:
		return parsed, true
	case float32:
		return float64(parsed), true
	case jsonNumber:
		result, err := strconv.ParseFloat(string(parsed), 64)
		return result, err == nil
	default:
		return 0, false
	}
}

func aggregateNetworkMetrics(peers []any) map[string]any {
	result := map[string]any{
		"online_peers":      0,
		"telemetry_nodes":   0,
		"active_tasks":      0,
		"queue_depth":       0,
		"logical_cpu_count": 0,
	}
	var cpuTotal, memoryTotal, storageTotal float64
	var cpuSamples, memorySamples, storageSamples int
	var latest time.Time

	for _, raw := range peers {
		peer, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		if online, ok := peer["online"].(bool); ok && online {
			result["online_peers"] = result["online_peers"].(int) + 1
		}
		if queue, ok := peer["task_queue"].([]any); ok {
			result["queue_depth"] = result["queue_depth"].(int) + len(queue)
		} else if queue, ok := peer["task_queue"].([]map[string]any); ok {
			result["queue_depth"] = result["queue_depth"].(int) + len(queue)
		}
		if activity := mapField(peer, "activity"); len(activity) > 0 {
			if tasks, ok := activity["active_tasks"].([]any); ok {
				result["active_tasks"] = result["active_tasks"].(int) + len(tasks)
			} else if tasks, ok := activity["active_tasks"].([]map[string]any); ok {
				result["active_tasks"] = result["active_tasks"].(int) + len(tasks)
			}
		}
		runtime := networkPeerRuntime(peer)
		if len(runtime) == 0 {
			continue
		}
		result["telemetry_nodes"] = result["telemetry_nodes"].(int) + 1
		if value, ok := networkFloatValue(runtime["system_cpu_percent"]); ok {
			cpuTotal += value
			cpuSamples++
		}
		if value, ok := networkFloatValue(runtime["system_memory_percent"]); ok {
			memoryTotal += value
			memorySamples++
		}
		if value, ok := networkFloatValue(runtime["storage_used_percent"]); ok {
			storageTotal += value
			storageSamples++
		}
		if value := networkInt64Value(runtime["logical_cpu_count"]); value > 0 {
			result["logical_cpu_count"] = result["logical_cpu_count"].(int) + int(value)
		}
		if timestamp := firstNetworkTimestamp(peer); timestamp.After(latest) {
			latest = timestamp
		}
	}
	if cpuSamples > 0 {
		result["system_cpu_percent"] = roundNetworkMetric(cpuTotal / float64(cpuSamples))
	}
	if memorySamples > 0 {
		result["system_memory_percent"] = roundNetworkMetric(memoryTotal / float64(memorySamples))
	}
	if storageSamples > 0 {
		result["storage_used_percent"] = roundNetworkMetric(storageTotal / float64(storageSamples))
	}
	if !latest.IsZero() {
		result["updated_utc"] = latest.Format(time.RFC3339Nano)
	}
	return result
}

func roundNetworkMetric(value float64) float64 {
	return math.Round(value*100) / 100
}
