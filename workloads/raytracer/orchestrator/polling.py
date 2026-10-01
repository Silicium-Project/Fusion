"""Polling of task results in the shared export directory.

Workers' results land as `result.<task_id>.json` and permanent failures as
lines of `dead_letters.ndjson`. A task attempt has a queue deadline, replaced
by a fresh execution deadline as soon as the scheduler reports it claimed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def poll_task_result_attempts(
    export_dir: Path,
    task_id: str,
    late_task_ids: list[str],
    deadline: float,
) -> tuple[str, dict[str, Any]] | None:
    """Return the first valid result, including one from a timed-out predecessor.

    Returns None while nothing is available; raises RuntimeError when the
    current attempt is dead-lettered and TimeoutError after `deadline`.
    """
    candidates = [*late_task_ids, task_id]
    for candidate_id in dict.fromkeys(candidates):
        result_path = export_dir / f"result.{candidate_id}.json"
        if not result_path.exists():
            continue
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if candidate_id != task_id and payload.get("success", True) is False:
            continue
        return candidate_id, payload

    # Only the current attempt can terminate the stage through a dead letter.
    # A dead-lettered predecessor remains historical evidence, not a new failure.
    dead_letters_path = export_dir / "dead_letters.ndjson"
    if dead_letters_path.exists():
        for line in dead_letters_path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and str(item.get("task_id", "")) == task_id:
                raise RuntimeError(
                    "network task dead-lettered: "
                    + str(item.get("last_error", "unknown_error"))
                    + f" ({task_id})"
                )
    if time.monotonic() > deadline:
        result_path = export_dir / f"result.{task_id}.json"
        raise TimeoutError(f"missing network result after deadline: {result_path}")
    return None


def refresh_attempt_deadline(
    export_dir: Path,
    token: dict[str, Any],
    execution_timeout_s: float,
) -> float:
    """Switch from the queue deadline to a fresh execution deadline once claimed."""
    execution_deadline = token.get("execution_deadline")
    if execution_deadline is not None:
        return float(execution_deadline)

    task_id = str(token["task_id"])
    task_path = export_dir / "tasks" / f"{task_id}.json"
    try:
        envelope = json.loads(task_path.read_text(encoding="utf-8")) if task_path.exists() else {}
    except json.JSONDecodeError:
        envelope = {}
    status = str(envelope.get("status", "")).strip().lower() if isinstance(envelope, dict) else ""
    if status in {"claimed", "dispatched", "in_progress", "processing", "running"}:
        execution_deadline = time.monotonic() + max(1.0, execution_timeout_s)
        token["execution_deadline"] = execution_deadline
        return float(execution_deadline)
    return float(token["queue_deadline"])
