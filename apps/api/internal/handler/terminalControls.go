package handler

import (
	"context"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/silicium/internal/models"
	"github.com/silicium/internal/silicium"
)

func terminalTaskControl(job models.Job, status, reason string, now time.Time, cfg silicium.RunnerConfig) silicium.TaskControl {
	action := "cancel"
	if status == "expired" {
		action = "expire"
	}
	if strings.TrimSpace(reason) == "" {
		reason = "job entered terminal state: " + status
	}
	control := silicium.TaskControl{
		ControlID:      fmt.Sprintf("%s-%s-terminal", job.SiliciumJobID, action),
		RootJobID:      job.SiliciumJobID,
		Action:         action,
		Reason:         reason,
		IssuerNode:     cfg.OrchestratorNodeID,
		IssuedUTC:      now.UTC().Format(time.RFC3339Nano),
		ReleaseChannel: cfg.ReleaseChannel,
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
	roots, err := silicium.ActiveControlRootIDs(ctx, cfg)
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
