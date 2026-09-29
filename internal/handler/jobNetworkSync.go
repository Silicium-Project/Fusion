// Synchronisation of jobs submitted directly to the network (outside this
// API) into the user's job list, and the network summary of a job.

package handler

import (
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

type networkJobAggregate struct {
	status, errorMessage, errorType, traceback string
	total, done, failed                        int
	latest                                     time.Time
	subtasks                                   []any
	roles                                      map[string]bool
	nodes                                      map[string]bool
	workload, kind                             string
}

func (h *Handler) syncNetworkJobs(userID uint) error {
	dir := filepath.Join(silicium.ConfigFromEnv().OrchestratorExportDir, "tasks")
	allowed, err := h.userNetworkJobIDs(userID)
	if err != nil {
		return err
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	aggs := map[string]*networkJobAggregate{}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		item := readJSONMap(filepath.Join(dir, entry.Name()))
		if len(item) == 0 {
			continue
		}
		id := networkRootJobID(item)
		if id == "" {
			continue
		}
		if _, owned := allowed[id]; !owned {
			continue
		}
		emitter := networkTaskEmitter(item)
		if emitter != "" && emitter != silicium.ConfigFromEnv().OrchestratorNodeID {
			continue
		}
		task, _ := item["task"].(map[string]any)
		failure := networkTaskFailureDetails(dir, item)
		status := strings.ToLower(stringValue(item["status"]))
		a := aggs[id]
		if a == nil {
			a = &networkJobAggregate{status: status, roles: map[string]bool{}, nodes: map[string]bool{}}
			aggs[id] = a
		}
		a.total++
		if status == "completed" {
			a.done++
		}
		if networkTaskFailed(status) {
			a.failed++
		}
		if !networkTerminalStatus(status) {
			a.status = status
		}
		if networkTaskFailed(status) {
			a.errorMessage = networkFailureDetail(failure)
			a.errorType = firstNetworkString(failure, "error_type")
			a.traceback = firstNetworkString(failure, "traceback", "error_traceback")
		}
		role := stringValue(item["required_role"])
		if role == "" {
			role = stringValue(item["role"])
		}
		if role != "" {
			a.roles[role] = true
		}
		node := stringValue(item["handled_by"])
		if node == "" {
			node = stringValue(item["claimed_by"])
		}
		if node != "" {
			a.nodes[node] = true
		}
		if taskWorkload := stringValue(task["workload"]); taskWorkload != "" {
			a.workload = taskWorkload
		}
		if taskKind := stringValue(task["kind"]); taskKind != "" {
			a.kind = taskKind
		}
		if len(a.subtasks) < 512 {
			timing := map[string]any{}
			if taskID := stringValue(item["task_id"]); taskID != "" {
				resultName := strings.NewReplacer("/", "_", "\\", "_", ":", "_").Replace(taskID)
				result := readJSONMap(filepath.Join(dir, "..", "result."+resultName+".json"))
				if value, ok := result["duration_ms"]; ok {
					timing["durationMs"] = value
				}
				if value, ok := result["performance"]; ok {
					timing["performance"] = value
				}
			}
			subtask := map[string]any{"taskId": stringValue(item["task_id"]), "status": status, "role": role, "handledBy": node, "submittedUtc": stringValue(item["submitted_utc"]), "claimedUtc": stringValue(item["claimed_utc"]), "handledUtc": stringValue(item["handled_utc"]), "fragmentIndex": task["fragment_index"], "fragmentCount": task["fragment_count"], "transport": item["transport"]}
			if detail := networkFailureDetail(failure); detail != "" {
				subtask["failureDetail"] = detail
			}
			if value := firstNetworkString(failure, "error", "error_message"); value != "" {
				subtask["error"] = value
			}
			if value := firstNetworkString(failure, "error_type"); value != "" {
				subtask["errorType"] = value
			}
			if value := firstNetworkString(failure, "traceback", "error_traceback"); value != "" {
				subtask["traceback"] = value
			}
			for key, value := range timing {
				subtask[key] = value
			}
			a.subtasks = append(a.subtasks, subtask)
		}
		if raw := stringValue(item["handled_utc"]); raw != "" {
			if parsed, parseErr := time.Parse(time.RFC3339, raw); parseErr == nil && parsed.After(a.latest) {
				a.latest = parsed
			}
		}
	}
	for id, a := range aggs {
		status := a.status
		if status == "" {
			status = "queued"
		}
		if a.failed > 0 && a.done < a.total {
			status = "failed"
		}
		if a.done == a.total && a.total > 0 {
			status = "completed"
		}
		now := a.latest
		if now.IsZero() {
			now = time.Now()
		}
		var job models.Job
		result := h.DB.Where("user_id = ? AND silicium_job_id = ?", userID, id).First(&job)
		if result.Error == nil {
			if strings.HasPrefix(job.InputPath, "rpc://") {
				updates := map[string]any{"status": status, "fragment_count": a.total, "updated_at": now, "network_metadata": networkJobMetadata(id, a, status)}
				if a.errorMessage != "" {
					updates["error_message"] = a.errorMessage
				} else if status == "completed" {
					updates["error_message"] = ""
				}
				if networkTerminalStatus(status) {
					updates["completed_at"] = now
				}
				h.DB.Model(&job).Updates(updates)
			}
			continue
		}
		// Unknown roots are deliberately ignored. They may belong to another
		// emitter or to an operator-level workload, and must never be imported
		// under the user who happened to open the task list.
	}
	return nil
}

func networkJobMetadata(id string, a *networkJobAggregate, status string) map[string]any {
	progress := 0.0
	if a.total > 0 {
		progress = float64(a.done) * 100 / float64(a.total)
	}
	roles := make([]string, 0, len(a.roles))
	for role := range a.roles {
		roles = append(roles, role)
	}
	nodes := make([]string, 0, len(a.nodes))
	for node := range a.nodes {
		nodes = append(nodes, node)
	}
	return map[string]any{"workId": id, "status": status, "progressPercent": progress, "total": a.total, "completed": a.done, "failed": a.failed, "workload": a.workload, "kind": a.kind, "roles": roles, "nodes": nodes, "subtasks": a.subtasks, "error": a.errorMessage, "errorType": a.errorType, "traceback": a.traceback, "failureDetail": a.errorMessage, "updatedUtc": a.latest.UTC().Format(time.RFC3339Nano)}
}

// networkJobSummary gives imported RPC jobs the same dashboard contract as a
// site-submitted job. The source of truth remains the task registry; no second
// frontend-specific task model is needed.
func (h *Handler) networkJobSummary(rootID string, fallback map[string]any) map[string]any {
	dir := filepath.Join(silicium.ConfigFromEnv().OrchestratorExportDir, "tasks")
	if fallback == nil {
		fallback = map[string]any{}
	}
	fragments := make([]map[string]any, 0)
	completed, failed, total := 0, 0, 0
	var latest string
	jobFailure := map[string]any{}
	entries, err := os.ReadDir(dir)
	if err == nil {
		for _, entry := range entries {
			if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
				continue
			}
			item := readJSONMap(filepath.Join(dir, entry.Name()))
			if len(item) == 0 {
				continue
			}
			id := stringValue(item["root_job_id"])
			task, _ := item["task"].(map[string]any)
			if id == "" {
				id = stringValue(task["root_job_id"])
			}
			if id == "" {
				id = stringValue(item["task_id"])
			}
			if marker := strings.Index(id, "-frag-"); marker > 0 {
				id = id[:marker]
			}
			if id != rootID {
				continue
			}
			status := strings.ToLower(stringValue(item["status"]))
			total++
			if status == "completed" {
				completed++
			}
			if networkTaskFailed(status) {
				failed++
			}
			if updated := stringValue(item["handled_utc"]); updated > latest {
				latest = updated
			}
			failure := networkTaskFailureDetails(dir, item)
			fragment := map[string]any{"taskId": stringValue(item["task_id"]), "status": status, "handledBy": stringValue(item["handled_by"]), "stage": stringValue(task["kind"]), "fragmentIndex": task["fragment_index"], "fragmentCount": task["fragment_count"]}
			if taskID := stringValue(item["task_id"]); taskID != "" {
				resultName := strings.NewReplacer("/", "_", "\\", "_", ":", "_").Replace(taskID)
				result := readJSONMap(filepath.Join(dir, "..", "result."+resultName+".json"))
				if performance, ok := result["performance"]; ok {
					fragment["performance"] = performance
				}
			}
			if detail := networkFailureDetail(failure); detail != "" {
				fragment["failureDetail"] = detail
				if networkTaskFailed(status) {
					jobFailure = failure
				}
			}
			if value := firstNetworkString(failure, "error", "error_message"); value != "" {
				fragment["error"] = value
			}
			if value := firstNetworkString(failure, "error_type"); value != "" {
				fragment["errorType"] = value
			}
			if value := firstNetworkString(failure, "traceback", "error_traceback"); value != "" {
				fragment["traceback"] = value
			}
			fragments = append(fragments, fragment)
		}
	}
	progress := 0.0
	if total > 0 {
		progress = float64(completed) * 100 / float64(total)
	}
	status := "running"
	if total == 0 {
		status = "queued"
	}
	if failed > 0 && completed < total {
		status = "failed"
	}
	if completed == total && total > 0 {
		status = "completed"
	}
	if total == 0 {
		if jobStatus, ok := fallback["status"].(string); ok && jobStatus != "" {
			status = jobStatus
		}
	}
	fallback["success"] = status == "completed"
	fallback["progress"] = progress
	fallback["stage"] = status
	fallback["updated_utc"] = latest
	fallback["job_id"] = rootID
	fallback["fragment_count"] = total
	fallback["fragments"] = fragments
	if detail := networkFailureDetail(jobFailure); detail != "" {
		fallback["error"] = firstNetworkString(jobFailure, "error", "error_message")
		fallback["error_type"] = firstNetworkString(jobFailure, "error_type")
		fallback["traceback"] = firstNetworkString(jobFailure, "traceback", "error_traceback")
		fallback["failure_detail"] = detail
	}
	return fallback
}
