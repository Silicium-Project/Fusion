#!/usr/bin/env python3
"""File-queue worker used by the Docker E2E scenario to claim and complete tasks (dev only)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path


SAFE_TASK_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe_task_id(task_id: str) -> str:
    return SAFE_TASK_ID_RE.sub("_", str(task_id or "").strip())


def _load_queue(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    items: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _claim_path(claim_dir: Path, task_id: str) -> Path:
    return claim_dir / f"{_safe_task_id(task_id)}.lock"


def _claim_task(claim_dir: Path, task_id: str, worker_id: str, role: str) -> bool:
    claim_dir.mkdir(parents=True, exist_ok=True)
    claim_path = _claim_path(claim_dir, task_id)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(claim_path), flags)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(
            {
                "task_id": task_id,
                "worker_id": worker_id,
                "role": role,
                "claimed_utc": _utc_now(),
            },
            stream,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")
    return True


def _required_roles(task: dict[str, object]) -> list[str]:
    value = task.get("required_roles", [])
    if isinstance(value, str):
        roles = [item.strip().lower() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        roles = [str(item).strip().lower() for item in value if str(item).strip()]
    else:
        roles = []
    return roles


def _candidate_queues(export_dir: Path, roles: list[str]) -> list[tuple[str, Path]]:
    queues = [(role, export_dir / f"tasks.{role}.queue.ndjson") for role in roles]
    if not queues:
        queues.append(("compute", export_dir / "tasks.compute.queue.ndjson"))
    return queues


def _process_task(export_dir: Path, task: dict[str, object], *, worker_id: str, role: str, transport: str) -> dict[str, object]:
    task_id = str(task.get("task_id", "")).strip()
    safe_task_id = _safe_task_id(task_id)
    task_path = export_dir / "tasks" / f"{safe_task_id}.json"
    result_path = export_dir / f"result.{safe_task_id}.json"
    logs_path = export_dir / f"logs.{safe_task_id}.json"
    completed_utc = _utc_now()

    updated_task = dict(task)
    updated_task["status"] = "completed"
    updated_task["completed_utc"] = completed_utc
    updated_task["handled_by"] = worker_id
    updated_task["worker_role"] = role
    updated_task["transport"] = transport
    _atomic_write(task_path, updated_task)

    result = {
        "schema_version": 1,
        "success": True,
        "task_id": task_id,
        "node_id": worker_id,
        "handled_by": worker_id,
        "worker_role": role,
        "transport": transport,
        "completed_utc": completed_utc,
        "task": task.get("task", {}),
        "queue": task.get("queue", ""),
        "required_roles": task.get("required_roles", []),
    }
    _atomic_write(result_path, result)
    _atomic_write(
        logs_path,
        {
            "schema_version": 1,
            "task_id": task_id,
            "worker_id": worker_id,
            "role": role,
            "transport": transport,
            "status": "completed",
            "completed_utc": completed_utc,
        },
    )
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consume Silicium queue entries inside Docker for e2e CI.")
    parser.add_argument("--export-dir", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--roles", default="compute")
    parser.add_argument("--expected-tasks", type=int, default=1)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--poll-s", type=float, default=0.25)
    parser.add_argument("--transport", default="docker-e2e")
    parser.add_argument("--task-prefix", default="", help="Only claim tasks whose task_id starts with this prefix.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    roles = [item.strip().lower() for item in str(args.roles).split(",") if item.strip()]
    if not roles:
        roles = ["compute"]

    claim_dir = export_dir / "claims"
    deadline = time.monotonic() + max(1.0, float(args.timeout_s))
    processed: list[dict[str, object]] = []
    seen: set[str] = set()
    task_prefix = str(args.task_prefix).strip()

    while len(processed) < max(1, int(args.expected_tasks)):
        if time.monotonic() > deadline:
            report = {
                "ok": False,
                "worker_id": args.worker_id,
                "roles": roles,
                "processed": processed,
                "error": "timeout_waiting_for_task",
                "timestamp_utc": _utc_now(),
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            return 1

        progressed = False
        for role, queue_path in _candidate_queues(export_dir, roles):
            for task in _load_queue(queue_path):
                task_id = str(task.get("task_id", "")).strip()
                if not task_id or task_id in seen:
                    continue
                if task_prefix and not task_id.startswith(task_prefix):
                    continue
                required_roles = _required_roles(task)
                if required_roles and role not in required_roles:
                    continue
                if not _claim_task(claim_dir, task_id, args.worker_id, role):
                    seen.add(task_id)
                    continue
                processed.append(
                    _process_task(
                        export_dir,
                        task,
                        worker_id=args.worker_id,
                        role=role,
                        transport=str(args.transport),
                    )
                )
                seen.add(task_id)
                progressed = True
                break
            if len(processed) >= max(1, int(args.expected_tasks)):
                break
        if not progressed:
            time.sleep(max(0.05, float(args.poll_s)))

    report = {
        "ok": True,
        "worker_id": args.worker_id,
        "roles": roles,
        "processed": processed,
        "timestamp_utc": _utc_now(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
