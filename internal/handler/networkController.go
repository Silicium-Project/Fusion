package handler

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"strings"
)

const (
	networkPeersPath   = "/var/lib/silicium/network/orchestrator/export/node.orchestrator-1.peers.json"
	updateManifestPath = "/var/lib/silicium/downloads/update-manifest.json"
)

func (h *Handler) GetNetworkPeers(w http.ResponseWriter, r *http.Request) {
	payload, err := loadNetworkPeers(networkPeersPath, updateManifestPath)
	if err != nil {
		http.Error(w, "Could not read peers registry: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		http.Error(w, "Could not encode peers registry", http.StatusInternalServerError)
	}
}

func loadNetworkPeers(peersPath, manifestPath string) (map[string]any, error) {
	raw, err := os.ReadFile(peersPath)
	if err != nil {
		return nil, err
	}
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return nil, err
	}

	channels := map[string]any{}
	if manifestRaw, manifestErr := os.ReadFile(manifestPath); manifestErr == nil {
		var manifest map[string]any
		if json.Unmarshal(manifestRaw, &manifest) == nil {
			channels, _ = manifest["channels"].(map[string]any)
			payload["release_manifest_generated_utc"] = manifest["generated_utc"]
		}
	}
	payload["release_channels"] = channels

	peers, _ := payload["peers"].([]any)
	for _, item := range peers {
		peer, ok := item.(map[string]any)
		if !ok {
			continue
		}
		version := stringField(peer, "app_version")
		channel := stringField(peer, "release_channel")
		if channel == "" {
			channel = "unknown"
		}
		latest := ""
		latestBuild := ""
		if release, ok := channels[channel].(map[string]any); ok {
			latest = stringField(release, "version")
			latestBuild = stringField(release, "build")
		}
		build := stringField(peer, "release_build")
		status := "current"
		outdated := false
		if stringField(peer, "node_id") == "orchestrator-1" {
			status = "server"
			outdated = false
		} else if version == "" || channel == "unknown" {
			status = "unknown"
			outdated = true
		} else if latest != "" && compareSemanticVersions(version, latest) < 0 {
			status = "outdated"
			outdated = true
		} else if version == latest && len(build) == 40 && len(latestBuild) == 40 && build != latestBuild {
			status = "outdated-build"
			outdated = true
		} else if latest == "" {
			status = "untracked-channel"
			outdated = true
		}
		peer["release_channel"] = channel
		peer["latest_version"] = latest
		peer["latest_build"] = latestBuild
		peer["version_status"] = status
		peer["outdated"] = outdated
	}
	return payload, nil
}

func stringField(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return strings.TrimSpace(value)
}

func compareSemanticVersions(left, right string) int {
	leftCore, leftPre := splitVersion(left)
	rightCore, rightPre := splitVersion(right)
	for index := 0; index < 3; index++ {
		if leftCore[index] < rightCore[index] {
			return -1
		}
		if leftCore[index] > rightCore[index] {
			return 1
		}
	}
	if leftPre == rightPre {
		return 0
	}
	if leftPre == "" {
		return 1
	}
	if rightPre == "" {
		return -1
	}
	leftParts := strings.Split(leftPre, ".")
	rightParts := strings.Split(rightPre, ".")
	limit := len(leftParts)
	if len(rightParts) > limit {
		limit = len(rightParts)
	}
	for index := 0; index < limit; index++ {
		leftPart, rightPart := "", ""
		if index < len(leftParts) {
			leftPart = leftParts[index]
		}
		if index < len(rightParts) {
			rightPart = rightParts[index]
		}
		leftNumber, leftNumeric := parseNumericPart(leftPart)
		rightNumber, rightNumeric := parseNumericPart(rightPart)
		if leftNumeric && rightNumeric {
			if leftNumber < rightNumber {
				return -1
			}
			if leftNumber > rightNumber {
				return 1
			}
			continue
		}
		if leftPart < rightPart {
			return -1
		}
		if leftPart > rightPart {
			return 1
		}
	}
	return 0
}

func splitVersion(value string) ([3]uint64, string) {
	value = strings.TrimPrefix(strings.TrimSpace(value), "v")
	sections := strings.SplitN(value, "-", 2)
	var core [3]uint64
	for index, part := range strings.Split(sections[0], ".") {
		if index >= len(core) {
			break
		}
		core[index], _ = strconv.ParseUint(part, 10, 64)
	}
	pre := ""
	if len(sections) == 2 {
		pre = sections[1]
	}
	return core, pre
}

func parseNumericPart(value string) (uint64, bool) {
	parsed, err := strconv.ParseUint(value, 10, 64)
	return parsed, err == nil
}
