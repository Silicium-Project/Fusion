"""Execution of one envelope: lifecycle, result files, receipts and follow-ups."""

from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any

from tools.node.daemon.performance import build_task_performance

from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    safe_id,
    safe_path_id,
    utc_now,
)


class HandlingMixin:
    """Run one task or request end to end."""

    def _clear_active_task_after_failure(self, item_id: str) -> None:
        with self._activity_lock:
            owns_active_task = bool(item_id) and any(
                safe_id(str(item.get("item_id", ""))) == item_id
                for item in self._active_tasks
            )
            if owns_active_task:
                self._active_tasks = []
        if not owns_active_task:
            return
        self._task_monitor_stop.set()
        monitor = self._task_monitor_thread
        if monitor is not None and monitor is not threading.current_thread():
            monitor.join(timeout=2.0)
        self._task_monitor_thread = None
        try:
            self.publish_runtime_state(announce=True)
        except Exception:
            pass

    def handle(self, envelope: dict[str, Any]) -> None:
        """Execute an envelope; on an unexpected error mark it failed and re-raise."""
        raw_item_id = str(envelope.get("request_id") or envelope.get("task_id") or "").strip()
        item_id = safe_id(raw_item_id) if raw_item_id else ""
        try:
            return self._handle(envelope)
        except Exception as exc:
            error_type = type(exc).__name__
            error = str(exc).strip() or error_type
            result = {
                "error": error,
                "error_type": error_type,
                "traceback": traceback.format_exc(),
            }
            if raw_item_id:
                try:
                    self.update_envelope_status(envelope, "failed", result)
                    self.remember_task_queue_envelope({**envelope, "status": "failed"})
                except Exception:
                    pass
            raise
        finally:
            self._clear_active_task_after_failure(item_id)

    def _handle(self, envelope: dict[str, Any]) -> None:
        """Execute one envelope and publish every artefact of its outcome.

        Steps, in order: task-control precheck, activity/monitor start,
        execution, performance and receipts, result/log files, terminal
        status, metrics/retry, events, result return, gossip, reputation,
        activity reset.
        """
        started = time.monotonic()
        started_unix_ms = int(time.time() * 1000)
        start_telemetry = self.telemetry_sampler.sample()
        kind = str(envelope.get("envelope_kind") or "task")
        active = self.task_activity(envelope)
        active["started_utc"] = utc_now()
        body_key = "request" if kind == "request" else "task"
        body = envelope.get(body_key) if isinstance(envelope.get(body_key), dict) else {}
        control_origin = str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or "")
        if self._close_if_already_controlled(envelope, control_origin):
            return
        self.runtime.begin_task()
        timeout_seconds = max(1, int(body.get("timeout_s", 300) or 300))
        progress_path = self.config.export_dir / f"task-progress.{safe_path_id(active['item_id'])}.json"
        envelope["_runtime_progress_path"] = str(progress_path)
        self._begin_active_task(envelope, active, start_telemetry, progress_path, started, timeout_seconds)
        result, item_id, ok, error = self._execute_envelope(kind, envelope)

        duration_ms = int((time.monotonic() - started) * 1000)
        self._task_monitor_stop.set()
        if self._task_monitor_thread is not None:
            self._task_monitor_thread.join(timeout=2.0)
        end_telemetry = self.telemetry_sampler.sample()
        self._telemetry = end_telemetry
        performance = build_task_performance(result, duration_ms, started_unix_ms, start_telemetry, end_telemetry)
        finished_utc = utc_now()
        self._finalize_result(envelope, body, result, active, performance, duration_ms, finished_utc)
        safe_item = safe_id(item_id)
        log_payload = self._write_result_files(safe_item, result, ok, error, duration_ms)
        terminal_status, cancelled, timed_out = self._terminal_status(item_id, control_origin, ok, error)
        self.update_envelope_status(envelope, terminal_status, result)
        self.remember_task_queue_envelope({**envelope, "status": terminal_status})
        self._append_rpc_event(terminal_status, safe_item, duration_ms, performance)
        self._record_outcome_metrics(envelope, ok, cancelled, timed_out, error, safe_item, duration_ms)
        self._append_outcome_event(kind, safe_item, ok, error, duration_ms)
        # Return the authoritative result before best-effort gossip. A slow or
        # unreachable peer must never delay the scheduler from advancing the
        # job to verification or to the next fragment.
        self.return_dispatched_result(envelope, result, log_payload)
        if ok and kind == "task":
            self._publish_task_outcome(safe_item, body, result)
        self.update_reputation(ok, kind, result)
        if ok and result.get("on_chain"):
            self.refresh_local_onchain_profile(force=True)
        self._finish_active_task(active, ok, error, duration_ms, terminal_status, performance)
        try:
            progress_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.publish_runtime_state(announce=True)

    def _close_if_already_controlled(self, envelope: dict[str, Any], control_origin: str) -> bool:
        """Mark the envelope cancelled/expired if a control already covers it."""
        item_id_for_control = str(envelope.get("request_id") or envelope.get("task_id") or "")
        existing_control = self.task_control_for(item_id_for_control, control_origin)
        if existing_control is None:
            return False
        self.update_envelope_status(
            envelope,
            "cancelled" if existing_control.get("action") == "cancel" else "expired",
            {"task_control": existing_control},
        )
        return True

    def _append_outcome_event(self, kind: str, safe_item: str, ok: bool, error: str, duration_ms: int) -> None:
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": kind,
                "item_id": safe_item,
                "ok": ok,
                "error": error,
                "duration_ms": duration_ms,
            },
        )

    def _begin_active_task(
        self,
        envelope: dict[str, Any],
        active: dict[str, Any],
        start_telemetry: dict[str, Any],
        progress_path: Path,
        started: float,
        timeout_seconds: int,
    ) -> None:
        """Publish the task as active (status ``running``) and start its monitor."""
        active.update(
            {
                "phase": "accepted",
                "progress_percent": 0.0,
                "progress_source": "measured",
                "elapsed_ms": 0,
                "eta_seconds": float(timeout_seconds),
                "completed_units": 0.0,
                "total_units": 0.0,
                "unit": "",
                "throughput_units_per_second": 0.0,
                "worker_threads": 0,
                "pixels_completed": 0,
                "pixels_total": 0,
                "attempt": int(envelope.get("attempt", 0) or 0),
                "max_retries": int(self.config.max_retries),
                "priority": str(envelope.get("priority", "normal")),
                "queued_utc": str(envelope.get("queued_utc") or envelope.get("created_utc") or ""),
                "resource_usage": start_telemetry,
            }
        )
        with self._activity_lock:
            self._active_tasks = [active]
        self._task_monitor_stop.clear()
        self._task_monitor_thread = threading.Thread(
            target=self._task_progress_monitor,
            args=(progress_path,),
            kwargs={"started_monotonic": started, "timeout_seconds": timeout_seconds},
            name=f"silicium-task-telemetry-{safe_path_id(active['item_id'])}",
            daemon=True,
        )
        self._task_monitor_thread.start()
        self.update_envelope_status(envelope, "running", {})
        self.remember_task_queue_envelope({**envelope, "status": "running"})
        self.publish_runtime_state(announce=True)

    def _execute_envelope(self, kind: str, envelope: dict[str, Any]) -> tuple[dict[str, Any], str, bool, str]:
        """Run the body; return ``(result, item_id, ok, error)``, never raising."""
        try:
            if kind == "request":
                result = self.handle_request(envelope)
                item_id = str(envelope.get("request_id", "request"))
            else:
                result = self.handle_task(envelope)
                item_id = str(envelope.get("task_id", "task"))
            ok = True
            error = ""
        except Exception as exc:
            item_id = str(envelope.get("request_id") or envelope.get("task_id") or "unknown")
            error_type = type(exc).__name__
            error = str(exc).strip() or error_type
            result = {
                "success": False,
                "error": error,
                "error_type": error_type,
                "traceback": traceback.format_exc(),
            }
            ok = False
        return result, item_id, ok, error

    def _finalize_result(
        self,
        envelope: dict[str, Any],
        body: dict[str, Any],
        result: dict[str, Any],
        active: dict[str, Any],
        performance: dict[str, Any],
        duration_ms: int,
        finished_utc: str,
    ) -> None:
        """Stamp node metadata, the compute receipt and (verify) the attestation."""
        result.update(
            {
                "schema_version": 1,
                "node_id": self.config.node_id,
                "roles": sorted(self.config.roles),
                "finished_utc": finished_utc,
                "duration_ms": duration_ms,
                "performance": performance,
            }
        )
        compute_receipt = self.build_compute_receipt(
            envelope,
            result,
            performance,
            started_utc=str(active.get("started_utc", "")),
            finished_utc=finished_utc,
        )
        result["compute_receipt"] = compute_receipt
        if str(result.get("role_result", "")).strip().lower() == "verify":
            result["receipt_attestation"] = self.build_receipt_attestation(envelope, body, result, finished_utc)

    def _write_result_files(
        self, safe_item: str, result: dict[str, Any], ok: bool, error: str, duration_ms: int
    ) -> dict[str, Any]:
        """Write ``result.<id>.json`` and ``logs.<id>.json``; return the log payload."""
        path_item = safe_path_id(safe_item)
        log_payload = {
            "schema_version": 1,
            "item_id": safe_item,
            "ok": ok,
            "error": error,
            "error_type": result.get("error_type", "") if not ok else "",
            "traceback": result.get("traceback", "") if not ok else "",
            "duration_ms": duration_ms,
        }
        atomic_write_json(self.config.export_dir / f"result.{path_item}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{path_item}.json", log_payload)
        return log_payload

    def _terminal_status(self, item_id: str, control_origin: str, ok: bool, error: str) -> tuple[str, bool, bool]:
        """Return ``(status, cancelled, timed_out)``; a control seen meanwhile wins."""
        active_control = self.task_control_for(item_id, control_origin)
        cancelled = active_control is not None or error.startswith("task_cancelled:")
        timed_out = error.startswith("task_timeout:")
        terminal_status = (
            "cancelled"
            if cancelled
            else "expired"
            if timed_out
            else "completed"
            if ok
            else "failed"
        )
        return terminal_status, cancelled, timed_out

    def _append_rpc_event(self, terminal_status: str, safe_item: str, duration_ms: int, performance: dict[str, Any]) -> None:
        try:
            append_jsonl(
                self.config.export_dir / "rpc.events.ndjson",
                {
                    "schema_version": 1,
                    "event": f"task.{terminal_status}",
                    "item_id": safe_item,
                    "timestamp_utc": utc_now(),
                    "handled_by": self.config.node_id,
                    "duration_ms": duration_ms,
                    "performance": performance,
                },
            )
        except Exception:
            # The RPC event journal is an optional wake-up optimisation. The
            # durable result file remains authoritative when it is unavailable.
            pass

    def _finish_active_task(
        self,
        active: dict[str, Any],
        ok: bool,
        error: str,
        duration_ms: int,
        terminal_status: str,
        performance: dict[str, Any],
    ) -> None:
        """Clear the active task and keep it as ``last_response``."""
        with self._activity_lock:
            completed_activity = dict(self._active_tasks[0]) if self._active_tasks else dict(active)
            self._active_tasks = []
            self._last_response = {
                **completed_activity,
                "ok": ok,
                "error": error,
                "duration_ms": duration_ms,
                "progress_percent": 100.0 if ok else completed_activity.get("progress_percent", 0.0),
                "phase": terminal_status,
                "timestamp_utc": utc_now(),
                "performance": performance,
            }
