package handler

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

func networkPeersFile() string {
	cfg := silicium.ConfigFromEnv()
	return filepath.Join(cfg.OrchestratorExportDir, "node."+cfg.OrchestratorNodeID+".peers.json")
}

func networkManifestFile() string {
	return filepath.Join(envDefault("SILICIUM_DOWNLOADS_DIR", "/var/lib/silicium/downloads"), "update-manifest.json")
}

// networkTaskFailed reports whether a task status of the node's task book
// counts as a failure (a cancellation does not).
func networkTaskFailed(status string) bool {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "failed", "dead_lettered", "expired":
		return true
	default:
		return false
	}
}

func networkRootJobID(item map[string]any) string {
	rootID := stringField(item, "root_job_id")
	if rootID == "" {
		if task, ok := item["task"].(map[string]any); ok {
			rootID = stringField(task, "root_job_id")
		}
	}
	if rootID == "" {
		rootID = stringField(item, "task_id")
	}
	if marker := strings.Index(rootID, "-frag-"); marker > 0 {
		rootID = rootID[:marker]
	}
	return rootID
}

func networkTaskEmitter(item map[string]any) string {
	emitter := stringField(item, "emitter_node_id")
	if emitter == "" {
		emitter = stringField(item, "origin_node_id")
	}
	if emitter == "" {
		if task, ok := item["task"].(map[string]any); ok {
			emitter = stringField(task, "emitter_node_id")
		}
	}
	return emitter
}

func controlTaskMap(control silicium.ControlTask) map[string]any {
	task := control.Task
	if task == nil {
		task = map[string]any{}
	}
	if _, exists := task["root_job_id"]; !exists {
		task["root_job_id"] = control.RootJobID
	}
	if _, exists := task["workload"]; !exists {
		task["workload"] = control.Workload
	}
	if _, exists := task["kind"]; !exists && len(control.RequiredRoles) > 0 {
		task["kind"] = control.RequiredRoles[0]
	}
	item := map[string]any{
		"task_id":     control.TaskID,
		"root_job_id": control.RootJobID,
		"status":      control.Status,
		"handled_by":  control.HandledBy,
		"task":        task,
	}
	if control.UpdatedUnix > 0 {
		item["handled_utc"] = time.Unix(control.UpdatedUnix, 0).UTC().Format(time.RFC3339)
	}
	if strings.TrimSpace(control.Error) != "" {
		item["error"] = control.Error
		item["failure_detail"] = control.Error
	}
	if strings.TrimSpace(control.ResultHash) != "" {
		item["result_hash"] = control.ResultHash
	}
	return item
}

func controlTaskWorkload(control silicium.ControlTask, item map[string]any) string {
	if workload := strings.TrimSpace(control.Workload); workload != "" {
		return workload
	}
	if task, ok := item["task"].(map[string]any); ok {
		if workload := stringField(task, "workload"); workload != "" {
			return workload
		}
	}
	return "raytracer"
}

func networkPeerCanCompute(peer map[string]any) bool {
	roles, exists := peer["roles"].([]any)
	if !exists {
		return true // Older peers default to compute,verify.
	}
	for _, raw := range roles {
		if role, ok := raw.(string); ok && strings.EqualFold(strings.TrimSpace(role), "compute") {
			return true
		}
	}
	return false
}

func networkPeerSupportsWorkload(peer map[string]any, workload string) bool {
	capacity := mapField(peer, "capacity")
	if capacity == nil {
		return true // Legacy workers did not advertise an allowlist.
	}
	items, exists := capacity["supported_workloads"].([]any)
	if !exists {
		return true
	}
	for _, raw := range items {
		if supported, ok := raw.(string); ok && strings.EqualFold(strings.TrimSpace(supported), workload) {
			return true
		}
	}
	return false
}

func networkQueueDiagnostic(queuedByWorkload map[string]int, oldestByWorkload map[string]int64, peers []map[string]any, peerErr error, oldestWait int64) map[string]any {
	queued := 0
	for _, count := range queuedByWorkload {
		queued += count
	}
	result := map[string]any{
		"queued":                 queued,
		"oldest_wait_seconds":    oldestWait,
		"online_compute_workers": 0,
		"compatible_workers":     0,
		"workloads":              []string{},
		"workload_diagnostics":   []map[string]any{},
		"reason":                 "",
	}
	if queued == 0 {
		return result
	}
	workloadNames := make([]string, 0, len(queuedByWorkload))
	for workload := range queuedByWorkload {
		workloadNames = append(workloadNames, workload)
	}
	sort.Strings(workloadNames)
	result["workloads"] = workloadNames
	if peerErr != nil {
		result["reason"] = "network_state_unavailable"
		diagnostics := make([]map[string]any, 0, len(workloadNames))
		for _, workload := range workloadNames {
			diagnostics = append(diagnostics, map[string]any{
				"workload":               workload,
				"queued":                 queuedByWorkload[workload],
				"oldest_wait_seconds":    oldestByWorkload[workload],
				"online_compute_workers": 0,
				"compatible_workers":     0,
				"reason":                 "network_state_unavailable",
			})
		}
		result["workload_diagnostics"] = diagnostics
		return result
	}
	onlineWorkers := make([]map[string]any, 0, len(peers))
	for _, peer := range peers {
		isOnline, _ := peer["online"].(bool)
		self, _ := peer["self"].(bool)
		if !isOnline || self || !networkPeerCanCompute(peer) {
			continue
		}
		onlineWorkers = append(onlineWorkers, peer)
	}
	diagnostics := make([]map[string]any, 0, len(workloadNames))
	compatiblePeers := map[string]struct{}{}
	workloadReasons := map[string]int{}
	for _, workload := range workloadNames {
		compatible := 0
		for workerIndex, peer := range onlineWorkers {
			if networkPeerSupportsWorkload(peer, workload) {
				compatible++
				peerID := stringField(peer, "peer_id")
				if peerID == "" {
					peerID = stringField(peer, "node_id")
				}
				if peerID == "" {
					peerID = strconv.Itoa(workerIndex)
				}
				compatiblePeers[peerID] = struct{}{}
			}
		}
		reason := "workers_not_claiming"
		if len(onlineWorkers) == 0 {
			reason = "no_compute_workers"
		} else if compatible == 0 {
			reason = "no_compatible_workers"
		}
		workloadReasons[reason]++
		diagnostics = append(diagnostics, map[string]any{
			"workload":               workload,
			"queued":                 queuedByWorkload[workload],
			"oldest_wait_seconds":    oldestByWorkload[workload],
			"online_compute_workers": len(onlineWorkers),
			"compatible_workers":     compatible,
			"reason":                 reason,
		})
	}
	result["online_compute_workers"] = len(onlineWorkers)
	result["compatible_workers"] = len(compatiblePeers)
	result["workload_diagnostics"] = diagnostics
	if len(workloadReasons) == 1 {
		for reason := range workloadReasons {
			result["reason"] = reason
		}
	} else {
		result["reason"] = "mixed_workload_blockers"
	}
	return result
}

func (h *Handler) userNetworkJobIDs(userID uint) (map[string]struct{}, error) {
	var jobs []models.Job
	if result := h.DB.Select("silicium_job_id").Where("user_id = ?", userID).Find(&jobs); result.Error != nil {
		return nil, result.Error
	}
	allowed := make(map[string]struct{}, len(jobs))
	for _, job := range jobs {
		if id := strings.TrimSpace(job.SiliciumJobID); id != "" {
			allowed[id] = struct{}{}
		}
	}
	return allowed, nil
}

func (h *Handler) GetNetworkTasks(w http.ResponseWriter, r *http.Request) {
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}
	allowed, err := h.userNetworkJobIDs(uint(userID))
	if err != nil {
		http.Error(w, "Could not scope network tasks", http.StatusInternalServerError)
		return
	}
	controlTasks, err := silicium.ListControlTasks(r.Context(), silicium.ConfigFromEnv(), "")
	if err != nil {
		http.Error(w, "Could not read Rust node task registry: "+err.Error(), http.StatusBadGateway)
		return
	}
	terminal := map[string]bool{"completed": true, "failed": true, "dead_lettered": true, "cancelled": true, "canceled": true, "expired": true, "finalized": true, "resolved": true}
	emitterID := silicium.ConfigFromEnv().OrchestratorNodeID
	active, recent := []map[string]any{}, []map[string]any{}
	groups := map[string]map[string]any{}
	queuedByWorkload := map[string]int{}
	oldestByWorkload := map[string]int64{}
	oldestWait := int64(0)
	nowUnix := time.Now().Unix()
	for _, controlTask := range controlTasks {
		item := controlTaskMap(controlTask)
		rootID := networkRootJobID(item)
		if _, owned := allowed[rootID]; !owned {
			continue
		}
		emitter := networkTaskEmitter(item)
		if emitter != "" && emitter != emitterID {
			continue
		}
		status := strings.ToLower(stringField(item, "status"))
		if status == "queued" || status == "proposed" {
			workload := controlTaskWorkload(controlTask, item)
			queuedByWorkload[workload]++
			created := controlTask.CreatedUnix
			if created <= 0 {
				created = controlTask.UpdatedUnix
			}
			if created > 0 {
				age := nowUnix - created
				if oldestWait == 0 || age > oldestWait {
					oldestWait = age
				}
				if oldestByWorkload[workload] == 0 || age > oldestByWorkload[workload] {
					oldestByWorkload[workload] = age
				}
			}
		}
		if terminal[status] {
			recent = append(recent, item)
		} else {
			active = append(active, item)
		}
		group := groups[rootID]
		if group == nil {
			group = map[string]any{"work_id": rootID, "status": status, "total": 0, "completed": 0, "failed": 0, "active": 0, "subtasks": []map[string]any{}, "updated_at": ""}
			groups[rootID] = group
		}
		group["total"] = group["total"].(int) + 1
		if status == "completed" {
			group["completed"] = group["completed"].(int) + 1
		}
		if networkTaskFailed(status) {
			group["failed"] = group["failed"].(int) + 1
		}
		if networkTaskFailed(status) {
			for _, key := range []string{"error", "error_message", "error_type", "traceback", "error_traceback", "failure_detail"} {
				if value, ok := item[key]; ok && strings.TrimSpace(stringValue(value)) != "" {
					group[key] = value
				}
			}
		}
		if !terminal[status] {
			group["active"] = group["active"].(int) + 1
			group["status"] = status
		}
		if task, ok := item["task"].(map[string]any); ok && group["workload"] == nil {
			group["workload"] = stringField(task, "workload")
			group["kind"] = stringField(task, "kind")
		}
		if emitter != "" && group["emitter_node_id"] == nil {
			group["emitter_node_id"] = emitter
		}
		if updated := stringField(item, "handled_utc"); updated != "" {
			group["updated_at"] = updated
		}
		subs := group["subtasks"].([]map[string]any)
		if len(subs) < 256 {
			tile := map[string]any{"task_id": stringField(item, "task_id"), "status": status, "handled_by": stringField(item, "handled_by")}
			for _, key := range []string{"error", "error_message", "error_type", "traceback", "error_traceback", "failure_detail"} {
				if value, ok := item[key]; ok && strings.TrimSpace(stringValue(value)) != "" {
					tile[key] = value
				}
			}
			if task, ok := item["task"].(map[string]any); ok {
				tile["fragment_index"] = task["fragment_index"]
				tile["fragment_count"] = task["fragment_count"]
				tile["stage"] = task["kind"]
			}
			subs = append(subs, tile)
		}
		group["subtasks"] = subs
	}
	workloads := make([]map[string]any, 0, len(groups))
	for _, group := range groups {
		workloads = append(workloads, group)
	}
	for _, group := range workloads {
		total, done := group["total"].(int), group["completed"].(int)
		failed := group["failed"].(int)
		if failed > 0 && done < total {
			group["status"] = "failed"
		} else if done == total && total > 0 {
			group["status"] = "completed"
		}
		if total > 0 {
			group["progress_percent"] = float64(done) * 100 / float64(total)
		}
	}
	activeWorkloads := make([]map[string]any, 0, len(workloads))
	for _, group := range workloads {
		if active, ok := group["active"].(int); ok && active > 0 {
			activeWorkloads = append(activeWorkloads, group)
		}
	}
	sort.Slice(activeWorkloads, func(i, j int) bool {
		return stringField(activeWorkloads[i], "updated_at") > stringField(activeWorkloads[j], "updated_at")
	})
	peerResponse, peerErr := silicium.ListControlPeers(r.Context(), silicium.ConfigFromEnv())
	var networkPeers []map[string]any
	if peerErr == nil {
		networkPeers, _ = peerResponse["peers"].([]map[string]any)
	}
	queue := networkQueueDiagnostic(queuedByWorkload, oldestByWorkload, networkPeers, peerErr, oldestWait)
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	_ = json.NewEncoder(w).Encode(map[string]any{"active": active, "recent": recent, "workloads": activeWorkloads, "emitter_node_id": emitterID, "queue": queue})
}

func (h *Handler) CancelNetworkTask(w http.ResponseWriter, r *http.Request) {
	rootID := strings.TrimSpace(mux.Vars(r)["id"])
	if rootID == "" {
		http.Error(w, "missing task id", http.StatusBadRequest)
		return
	}
	userID, ok := userIDFromRequest(r)
	if !ok {
		http.Error(w, "User ID not found in context", http.StatusUnauthorized)
		return
	}
	var job models.Job
	if result := h.DB.Where("user_id = ? AND silicium_job_id = ?", userID, rootID).First(&job); result.Error != nil {
		http.Error(w, "Network task not found", http.StatusNotFound)
		return
	}
	changed, err := silicium.CancelControlWorkload(r.Context(), silicium.ConfigFromEnv(), rootID)
	if err != nil {
		http.Error(w, "Could not cancel Rust node tasks: "+err.Error(), http.StatusBadGateway)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "work_id": rootID, "cancelled": changed})
}

func (h *Handler) GetNetworkPeers(w http.ResponseWriter, r *http.Request) {
	payload, err := silicium.ListControlPeers(r.Context(), silicium.ConfigFromEnv())
	if err != nil {
		http.Error(w, "Could not read Rust node peers registry: "+err.Error(), http.StatusBadGateway)
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
	registryNodeID := networkRegistryNodeID(peersPath)
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
		self, _ := peer["self"].(bool)
		if self || (registryNodeID != "" && stringField(peer, "node_id") == registryNodeID) {
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
	enrichNetworkPeers(payload, peersPath)
	return payload, nil
}

func networkRegistryNodeID(peersPath string) string {
	name := filepath.Base(peersPath)
	if !strings.HasPrefix(name, "node.") || !strings.HasSuffix(name, ".peers.json") {
		return ""
	}
	return strings.TrimSuffix(strings.TrimPrefix(name, "node."), ".peers.json")
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
