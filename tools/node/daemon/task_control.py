"""Signed task controls (cancel/expire): validate, apply and look up."""

from __future__ import annotations

import json
import threading
from typing import Any

from tools.node.util import append_jsonl, read_json, safe_id, safe_path_id, utc_now


class TaskControlMixin:
    """Apply cancellation and expiry controls to queued and running work."""

    def _load_task_controls(self) -> None:
        """Reload the last 2048 persisted controls (called from __init__)."""
        self._task_controls_lock = threading.Lock()
        self._task_controls: dict[str, dict[str, Any]] = {}
        self._task_controls_path = self.config.export_dir / "task-controls.ndjson"
        if self._task_controls_path.exists():
            for line in self._task_controls_path.read_text(encoding="utf-8").splitlines()[-2048:]:
                try:
                    control = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(control, dict) and str(control.get("control_id", "")).strip():
                    self._task_controls[str(control["control_id"])] = control

    def validate_task_control(self, payload: Any, *, signed_by: str) -> bool:
        """Whether ``payload`` is a well-formed control issued by ``signed_by``."""
        if not isinstance(payload, dict):
            return False
        root_job_id = str(payload.get("root_job_id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        issuer = str(payload.get("issuer_node_id", "")).strip()
        control_id = str(payload.get("control_id", "")).strip()
        release_channel = str(payload.get("release_channel", "") or "").strip().lower()
        return bool(
            root_job_id
            and control_id
            and action in {"cancel", "expire"}
            and issuer
            and safe_id(issuer) == safe_id(signed_by)
            and (not release_channel or release_channel == self.config.release_channel)
        )

    def apply_task_control(self, payload: dict[str, Any], *, signed_by: str) -> bool:
        """Record a control and cancel/expire matching active and queued work.

        Returns False when the control is invalid, True when it is (or was
        already) applied. Queued envelopes are swept in a background thread.
        """
        if not self.validate_task_control(payload, signed_by=signed_by):
            return False
        control = dict(payload)
        root_job_id = safe_id(str(control["root_job_id"]))
        control["root_job_id"] = root_job_id
        control["signed_by"] = safe_id(signed_by)
        control["received_utc"] = utc_now()
        with self._task_controls_lock:
            if str(control["control_id"]) in self._task_controls:
                return True
            self._task_controls[str(control["control_id"])] = control
        append_jsonl(self._task_controls_path, control)

        if self._mark_controlled_active_tasks(control, root_job_id, signed_by):
            self.runtime.cancel_task(str(control.get("reason", "task cancelled")))

        threading.Thread(
            target=self._sweep_controlled_envelopes,
            args=(control, root_job_id, signed_by),
            name=f"silicium-task-control-sweep-{safe_path_id(root_job_id)}",
            daemon=True,
        ).start()
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "task_control",
                "item_id": root_job_id,
                "action": str(control.get("action")),
                "control_id": str(control.get("control_id")),
                "signed_by": safe_id(signed_by),
            },
        )
        self.publish_runtime_state(announce=True)
        return True

    def _mark_controlled_active_tasks(self, control: dict[str, Any], root_job_id: str, signed_by: str) -> bool:
        """Flag active tasks of ``root_job_id`` issued by ``signed_by`` as cancelling."""
        matched_active = False
        with self._activity_lock:
            for activity in self._active_tasks:
                item_id = safe_id(str(activity.get("item_id", "")))
                origin_raw = str(activity.get("origin_node_id", "")).strip()
                origin = safe_id(origin_raw) if origin_raw else ""
                authorized = origin == safe_id(signed_by) if origin else safe_id(signed_by) == self.config.node_id
                if authorized and (item_id == root_job_id or item_id.startswith(root_job_id + "-")):
                    activity.update(
                        {
                            "phase": "cancelling",
                            "cancel_reason": str(control.get("reason", "")),
                            "control_id": str(control.get("control_id", "")),
                        }
                    )
                    matched_active = True
        return matched_active

    def _sweep_controlled_envelopes(self, control: dict[str, Any], root_job_id: str, signed_by: str) -> None:
        """Mark queued tasks/requests of ``root_job_id`` cancelled or expired."""
        pattern = f"{safe_path_id(root_job_id)}*.json"
        for directory in (self.config.export_dir / "tasks", self.config.export_dir / "requests"):
            if not directory.exists():
                continue
            for item_path in directory.glob(pattern):
                envelope = read_json(item_path, {})
                if not isinstance(envelope, dict):
                    continue
                item_id = safe_id(str(envelope.get("task_id") or envelope.get("request_id") or ""))
                origin_raw = str(envelope.get("origin_node_id") or envelope.get("dispatched_by") or "").strip()
                origin = safe_id(origin_raw) if origin_raw else ""
                if item_id != root_job_id and not item_id.startswith(root_job_id + "-"):
                    continue
                if origin != safe_id(signed_by) and not (not origin and safe_id(signed_by) == self.config.node_id):
                    continue
                self.update_envelope_status(
                    envelope,
                    "cancelled" if str(control.get("action")) == "cancel" else "expired",
                    {"task_control": control},
                )

    def task_control_for(self, item_id: str, origin_node_id: str = "") -> dict[str, Any] | None:
        """Latest control covering ``item_id`` from an authorised issuer, if any."""
        normalized = safe_id(item_id)
        origin_raw = str(origin_node_id).strip()
        origin = safe_id(origin_raw) if origin_raw else ""
        with self._task_controls_lock:
            controls = list(self._task_controls.values())
        for control in reversed(controls):
            root_job_id = safe_id(str(control.get("root_job_id", "")))
            signed_by = safe_id(str(control.get("signed_by") or control.get("issuer_node_id") or ""))
            authorized = signed_by == origin if origin else signed_by == self.config.node_id
            if authorized and (normalized == root_job_id or normalized.startswith(root_job_id + "-")):
                return dict(control)
        return None
