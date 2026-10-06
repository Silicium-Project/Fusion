package silicium

// Waiting for the reassembled image of a finished raytracer job.
//
// The Rust node reports every fragment task as "completed" once its result
// is verified and finalized in the task book. The final image does not exist
// yet at that moment: the orchestrator still downloads each tile image from
// the worker that rendered it, checks it against the verified milestones,
// reassembles the job, then copies the result to
// `<job dir>/reassembled/render.ppm` and writes `raytracer-summary.json`.
// The BackEnd therefore waits for that summary before reading the result.

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// defaultResultWait bounds the wait for the reassembled image after the
// fragments are finalized (downloads from workers plus reassembly).
const defaultResultWait = 3 * time.Minute

// resultPollInterval is the delay between two reads of the job summary.
const resultPollInterval = 500 * time.Millisecond

// resultWaitTimeout returns `SILICIUM_RESULT_WAIT_S` seconds, or the default.
func resultWaitTimeout() time.Duration {
	value := strings.TrimSpace(os.Getenv("SILICIUM_RESULT_WAIT_S"))
	if seconds, err := strconv.Atoi(value); err == nil && seconds > 0 {
		return time.Duration(seconds) * time.Second
	}
	return defaultResultWait
}

// waitForReassembledImage returns nil once `resultPath` is a regular file and
// the job summary does not report a failure. It returns the node's error when
// the summary reports one, and `raytracer_result_timeout` when the image does
// not appear within `timeout`.
func waitForReassembledImage(ctx context.Context, resultPath, summaryPath string, timeout time.Duration) error {
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()
	ticker := time.NewTicker(resultPollInterval)
	defer ticker.Stop()
	for {
		summary := parseRaytracerSummary(summaryPath)
		if summary.Status == "failed" {
			message := summary.ErrorMessage
			if message == "" {
				message = "raytracer_reassembly_failed"
			}
			return fmt.Errorf("%s", message)
		}
		if info, err := os.Stat(resultPath); err == nil && info.Mode().IsRegular() {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return fmt.Errorf("raytracer_result_timeout: %s", resultPath)
		case <-ticker.C:
		}
	}
}
