package handler

import (
	"path/filepath"
	"strings"
)

const networkFailureDetailLimit = 64 * 1024

func networkTaskFailed(status string) bool {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "failed", "dead_lettered", "expired":
		return true
	default:
		return false
	}
}

// networkTaskFailureDetails joins the durable task envelope with the result
// and log artifacts written by a worker. The envelope is updated before the
// result is returned to the emitter, so reading all three makes this endpoint
// work for both local workers and remotely dispatched results.
func networkTaskFailureDetails(tasksDir string, item map[string]any) map[string]any {
	details := map[string]any{}
	mergeNetworkFailureFields(details, item)

	taskID := stringField(item, "task_id")
	if taskID == "" {
		return details
	}
	resultName := strings.NewReplacer("/", "_", "\\", "_", ":", "_").Replace(taskID)
	artifactDir := filepath.Dir(tasksDir)
	for _, name := range []string{
		filepath.Join(artifactDir, "result."+resultName+".json"),
		filepath.Join(artifactDir, "logs."+resultName+".json"),
	} {
		artifact := readJSONMap(name)
		mergeNetworkFailureFields(details, artifact)
	}
	if detail := networkFailureDetail(details); detail != "" {
		details["failure_detail"] = detail
	}
	return details
}

func mergeNetworkFailureFields(target, source map[string]any) {
	if len(source) == 0 {
		return
	}
	for _, key := range []string{"error", "error_message", "error_type", "traceback", "error_traceback"} {
		value, ok := source[key].(string)
		value = boundedNetworkFailureText(value)
		if ok && strings.TrimSpace(value) != "" {
			target[key] = value
		}
	}
}

func networkFailureDetail(details map[string]any) string {
	message := firstNetworkString(details, "error", "error_message")
	errorType := firstNetworkString(details, "error_type")
	traceback := firstNetworkString(details, "traceback", "error_traceback")
	if message == "" && traceback == "" {
		return ""
	}
	if errorType != "" && !strings.Contains(message, errorType) {
		message = errorType + ": " + message
	}
	if traceback == "" {
		return boundedNetworkFailureText(message)
	}
	if message == "" || strings.Contains(traceback, message) {
		return boundedNetworkFailureText(traceback)
	}
	return boundedNetworkFailureText(message + "\n\nTraceback worker:\n" + traceback)
}

func firstNetworkString(values map[string]any, keys ...string) string {
	for _, key := range keys {
		if value, ok := values[key].(string); ok && strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func boundedNetworkFailureText(value string) string {
	value = strings.TrimSpace(value)
	if len(value) <= networkFailureDetailLimit {
		return value
	}
	marker := "\n[… détail d’erreur tronqué par le serveur …]"
	return strings.TrimSpace(value[:networkFailureDetailLimit-len(marker)]) + marker
}
