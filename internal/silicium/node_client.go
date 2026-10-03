package silicium

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// ControlTask is the stable subset of the Rust node control API consumed by
// the BackEnd. The public BackEnd API intentionally remains independent from
// this transport representation.
type ControlTask struct {
	TaskID        string         `json:"task_id"`
	RootJobID     string         `json:"root_job_id"`
	Workload      string         `json:"workload"`
	RequiredRoles []string       `json:"required_roles"`
	Status        string         `json:"status"`
	HandledBy     string         `json:"handled_by"`
	Error         string         `json:"error"`
	ResultHash    string         `json:"result_hash"`
	CreatedUnix   int64          `json:"created_unix"`
	UpdatedUnix   int64          `json:"updated_unix"`
	Task          map[string]any `json:"task"`
}

// ControlTaskSubmission is the public request contract of POST /v1/tasks.
// ScenePath is translated to the host-visible shared-volume path before the
// request when the BackEnd runs in Compose; OutputPath remains a compatibility
// projection consumed by the BackEnd after the Rust node finishes.
type ControlTaskSubmission struct {
	TaskID        string   `json:"task_id"`
	RootJobID     string   `json:"root_job_id"`
	Workload      string   `json:"workload"`
	RequiredRoles []string `json:"required_roles"`
	ScenePath     string   `json:"scene_path"`
	OutputPath    string   `json:"output_path"`
	Seed          string   `json:"seed"`
	FragmentCount int      `json:"fragment_count,omitempty"`
}

type controlTasksResponse struct {
	Tasks []ControlTask `json:"tasks"`
}

type controlPeersResponse struct {
	Peers   []map[string]any `json:"peers"`
	Metrics map[string]any   `json:"metrics"`
}

type controlCancelResponse struct {
	Cancelled int `json:"cancelled"`
}

func nodeControlURL(cfg RunnerConfig, path string) (string, error) {
	base := strings.TrimRight(strings.TrimSpace(cfg.NodeAPIURL), "/")
	if base == "" {
		return "", fmt.Errorf("SILICIUM_NODE_API_URL is required")
	}
	return base + path, nil
}

func nodeControlRequest(ctx context.Context, cfg RunnerConfig, method, path string, body any, output any) error {
	endpoint, err := nodeControlURL(cfg, path)
	if err != nil {
		return err
	}
	var payload *bytes.Reader
	if body == nil {
		payload = bytes.NewReader(nil)
	} else {
		raw, marshalErr := json.Marshal(body)
		if marshalErr != nil {
			return marshalErr
		}
		payload = bytes.NewReader(raw)
	}
	request, err := http.NewRequestWithContext(ctx, method, endpoint, payload)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/json")
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if token := strings.TrimSpace(cfg.NodeControlToken); token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	response, err := (&http.Client{Timeout: 12 * time.Second}).Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		var failure map[string]any
		_ = json.NewDecoder(response.Body).Decode(&failure)
		if message, ok := failure["error"].(string); ok && strings.TrimSpace(message) != "" {
			return fmt.Errorf("node control %s %s: %s", method, path, message)
		}
		return fmt.Errorf("node control %s %s: %s", method, path, response.Status)
	}
	if output == nil || response.StatusCode == http.StatusNoContent {
		return nil
	}
	return json.NewDecoder(response.Body).Decode(output)
}

func ListControlTasks(ctx context.Context, cfg RunnerConfig, rootJobID string) ([]ControlTask, error) {
	path := "/v1/tasks"
	if rootJobID = strings.TrimSpace(rootJobID); rootJobID != "" {
		path += "?root_job_id=" + url.QueryEscape(rootJobID)
	}
	var response controlTasksResponse
	if err := nodeControlRequest(ctx, cfg, http.MethodGet, path, nil, &response); err != nil {
		return nil, err
	}
	return response.Tasks, nil
}

func SubmitControlTask(ctx context.Context, cfg RunnerConfig, task ControlTaskSubmission) (ControlTask, error) {
	var response ControlTask
	if err := nodeControlRequest(ctx, cfg, http.MethodPost, "/v1/tasks", task, &response); err != nil {
		return ControlTask{}, err
	}
	return response, nil
}

func ListControlPeers(ctx context.Context, cfg RunnerConfig) (map[string]any, error) {
	var response controlPeersResponse
	if err := nodeControlRequest(ctx, cfg, http.MethodGet, "/v1/peers", nil, &response); err != nil {
		return nil, err
	}
	return map[string]any{
		"peers":   response.Peers,
		"metrics": response.Metrics,
	}, nil
}

func CancelControlWorkload(ctx context.Context, cfg RunnerConfig, rootJobID string) (int, error) {
	var response controlCancelResponse
	path := "/v1/workloads/" + url.PathEscape(strings.TrimSpace(rootJobID)) + "/cancel"
	if err := nodeControlRequest(ctx, cfg, http.MethodPost, path, nil, &response); err != nil {
		return 0, err
	}
	return response.Cancelled, nil
}

func ActiveControlRootIDs(ctx context.Context, cfg RunnerConfig) (map[string]bool, error) {
	tasks, err := ListControlTasks(ctx, cfg, "")
	if err != nil {
		return nil, err
	}
	roots := make(map[string]bool)
	for _, task := range tasks {
		switch strings.ToLower(strings.TrimSpace(task.Status)) {
		case "queued", "proposed", "claimed", "dispatched", "running", "retrying":
			if root := strings.TrimSpace(task.RootJobID); root != "" {
				roots[root] = true
			}
		}
	}
	return roots, nil
}
