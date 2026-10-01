"""Background monitor that publishes progress/telemetry of the running task."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.node.util import read_json, utc_now


class ProgressMixin:
    """Track the progress of the task being executed."""

    def _task_progress_monitor(
        self,
        progress_path: Path,
        *,
        started_monotonic: float,
        timeout_seconds: int,
    ) -> None:
        sequence = 0
        while not self._task_monitor_stop.wait(1.0):
            sequence += 1
            self._telemetry = self.telemetry_sampler.sample()
            elapsed = max(0.0, time.monotonic() - started_monotonic)
            progress = read_json(progress_path, {})
            updates: dict[str, Any] = {
                "elapsed_ms": round(elapsed * 1000),
                "resource_usage": self.telemetry_snapshot(),
                "telemetry_sequence": sequence,
                "updated_utc": utc_now(),
            }
            if isinstance(progress, dict) and progress.get("schema") == "silicium.task-progress.v1":
                updates.update(
                    {
                        "phase": str(progress.get("phase", "executing")),
                        "progress_percent": max(
                            0.0, min(100.0, float(progress.get("progress_percent", 0.0) or 0.0))
                        ),
                        "progress_source": "measured",
                        "completed_units": float(progress.get("completed_units", 0.0) or 0.0),
                        "total_units": float(progress.get("total_units", 0.0) or 0.0),
                        "unit": str(progress.get("unit", "")),
                        "throughput_units_per_second": float(
                            progress.get("throughput_units_per_second", 0.0) or 0.0
                        ),
                        "eta_seconds": float(progress.get("eta_seconds", 0.0) or 0.0),
                        "worker_threads": int(progress.get("threads", 0) or 0),
                        "pixels_completed": int(progress.get("pixels_completed", 0) or 0),
                        "pixels_total": int(progress.get("pixels_total", 0) or 0),
                    }
                )
            else:
                estimated = min(
                    90.0,
                    10.0 + 80.0 * elapsed / max(1.0, float(timeout_seconds)),
                )
                updates.update(
                    {
                        "progress_percent": estimated,
                        "progress_source": "estimated",
                        "eta_seconds": max(0.0, timeout_seconds - elapsed),
                    }
                )
            self.update_active_task(**updates)
            self.peer_network.set_local_profile(activity=self.activity_snapshot())
            if sequence % 2 == 0:
                self.write_metrics()
                self.write_heartbeat()
                self.peer_network.schedule_announce()
