// Blockchain trace of a job: anchoring after completion, dashboard view.
//
// When SILICIUM_DEVNET_TRACE=1, every completed job is anchored on Solana
// by internal/chainproof (one Memo transaction carrying the Merkle root of
// the job's signed task traces). A failure to anchor never fails the job:
// the computation is done and paid for; the trace says why it is missing.

package handler

import (
	"context"
	"log"
	"time"

	"github.com/silicium/internal/chainproof"
	"github.com/silicium/internal/models"
)

// anchorTimeout bounds one anchoring (blockhash, send, confirmation).
const anchorTimeout = 3 * time.Minute

// anchorJobOnChain anchors a completed job and records its trace path and
// transaction signature on the job. It is called from the job's own
// goroutine, after the result is saved, so the user is never kept waiting.
func (h *Handler) anchorJobOnChain(jobID uint) {
	cfg := chainproof.ConfigFromEnv()
	if !cfg.Enabled || h.DB == nil {
		return
	}
	var job models.Job
	if result := h.DB.First(&job, jobID); result.Error != nil || job.Status != "completed" {
		return
	}
	if job.SummaryPath == "" || job.ResultPath == "" {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), anchorTimeout)
	defer cancel()
	tracePath, trace, err := chainproof.Anchor(ctx, cfg, job.SummaryPath, job.ResultPath)
	updates := map[string]any{}
	if tracePath != "" {
		updates["devnet_trace_path"] = tracePath
	}
	if len(trace.Signatures) > 0 {
		// devnet_job holds the transaction that anchors the job.
		updates["devnet_job"] = trace.Signatures[0]
	}
	if len(updates) > 0 {
		h.DB.Model(&models.Job{}).Where("id = ?", jobID).Updates(updates)
	}
	if err != nil {
		log.Printf("job %d: blockchain trace not anchored: %v", jobID, err)
	}
}

// devnetDashboard is the `devnet` block of the job dashboard: the anchoring
// status, the transaction to open in an explorer, and every task with its
// Merkle proof so the site can check it against the on-chain root.
func devnetDashboard(job models.Job, summary map[string]any) map[string]any {
	trace := readJSONMap(job.DevnetTracePath)
	// Jobs run by the former Python orchestrator described the trace in the
	// summary; keep showing them.
	legacy, _ := summary["devnet_trace"].(map[string]any)
	if len(trace) == 0 {
		if inner, ok := legacy["trace"].(map[string]any); ok {
			trace = inner
		}
	}
	enabled := chainproof.ConfigFromEnv().Enabled || len(trace) > 0
	status, _ := trace["status"].(string)
	ok, _ := trace["ok"].(bool)
	if status == "" && legacy != nil {
		status, _ = legacy["status"].(string)
		ok, _ = legacy["ok"].(bool)
	}
	if status == "" {
		status = "not_requested"
		if enabled && job.Status == "completed" {
			status = chainproof.StatusPending
		}
	}
	return map[string]any{
		"enabled":     enabled,
		"ok":          ok,
		"status":      status,
		"job":         trace["job"],
		"programId":   trace["program_id"],
		"rpc":         trace["rpc"],
		"cluster":     trace["cluster"],
		"payer":       trace["payer"],
		"signatures":  trace["signatures"],
		"explorerUrl": trace["explorer_url"],
		"memo":        trace["memo"],
		"merkleRoot":  trace["merkle_root"],
		"finalSha256": trace["final_sha256"],
		"taskCount":   trace["task_count"],
		"fragments":   trace["fragments"],
		"splitTree":   trace["split_tree"],
		"updatedUtc":  trace["updated_utc"],
		"error":       trace["error"],
	}
}
