package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

var activeTaskStatuses = map[string]bool{
	"assigned":   true,
	"claimed":    true,
	"dispatched": true,
	"queued":     true,
	"retrying":   true,
	"running":    true,
}

func activeTaskRootIDs(exportDir string) (map[string]bool, error) {
	entries, err := os.ReadDir(filepath.Join(exportDir, "tasks"))
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]bool{}, nil
		}
		return nil, err
	}
	roots := make(map[string]bool)
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(exportDir, "tasks", entry.Name()))
		if err != nil {
			continue
		}
		var envelope map[string]any
		if json.Unmarshal(raw, &envelope) != nil || !activeTaskStatuses[strings.ToLower(stringValue(envelope["status"]))] {
			continue
		}
		rootID := stringValue(envelope["root_job_id"])
		task, _ := envelope["task"].(map[string]any)
		if rootID == "" && task != nil {
			rootID = stringValue(task["root_job_id"])
		}
		taskID := stringValue(envelope["task_id"])
		if rootID == "" {
			if marker := strings.Index(taskID, "-frag-"); marker > 0 {
				rootID = taskID[:marker]
			} else {
				rootID = taskID
			}
		}
		if rootID != "" {
			roots[rootID] = true
		}
	}
	return roots, nil
}

func terminalTaskControl(job models.Job, status, reason string, now time.Time, cfg silicium.RunnerConfig) silicium.TaskControl {
	action := "cancel"
	if status == "expired" {
		action = "expire"
	}
	if strings.TrimSpace(reason) == "" {
		reason = "job entered terminal state: " + status
	}
	control := silicium.TaskControl{
		ControlID:  fmt.Sprintf("%s-%s-terminal", job.SiliciumJobID, action),
		RootJobID:  job.SiliciumJobID,
		Action:     action,
		Reason:     reason,
		IssuerNode: cfg.OrchestratorNodeID,
		IssuedUTC:  now.UTC().Format(time.RFC3339Nano),
	}
	if action == "expire" && job.DeadlineAt != nil {
		control.DeadlineUTC = job.DeadlineAt.UTC().Format(time.RFC3339Nano)
	}
	return control
}

func publishTerminalTaskControl(ctx context.Context, job models.Job, status, reason string) error {
	cfg := silicium.ConfigFromEnv()
	control := terminalTaskControl(job, status, reason, time.Now(), cfg)
	return silicium.PublishTaskControl(ctx, cfg, control)
}

func (h *Handler) ReconcileTerminalJobControls(ctx context.Context) {
	cfg := silicium.ConfigFromEnv()
	roots, err := activeTaskRootIDs(cfg.OrchestratorExportDir)
	if err != nil {
		log.Printf("terminal task-control reconciliation skipped: %v", err)
		return
	}
	if len(roots) == 0 {
		return
	}
	rootIDs := make([]string, 0, len(roots))
	for rootID := range roots {
		rootIDs = append(rootIDs, rootID)
	}
	var jobs []models.Job
	result := h.DB.WithContext(ctx).
		Where("silicium_job_id IN ? AND status IN ?", rootIDs, []string{"failed", "cancelled", "expired"}).
		Find(&jobs)
	if result.Error != nil {
		log.Printf("terminal task-control reconciliation query failed: %v", result.Error)
		return
	}
	for _, job := range jobs {
		signalCtx, cancel := context.WithTimeout(ctx, 12*time.Second)
		err := publishTerminalTaskControl(signalCtx, job, job.Status, job.ErrorMessage)
		cancel()
		if err != nil {
			log.Printf("terminal task-control reconciliation failed for %s: %v", job.SiliciumJobID, err)
		}
	}
}

func (h *Handler) RunTerminalJobControlReconciler(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 30 * time.Second
	}
	h.ReconcileTerminalJobControls(ctx)
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			h.ReconcileTerminalJobControls(ctx)
		}
	}
}

func stringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}
