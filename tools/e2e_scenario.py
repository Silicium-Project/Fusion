#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.rpc_client import RpcClient


DEFAULT_TASKS: list[dict[str, Any]] = [
    {
        "task_id": "web-compute-a",
        "submit": "web",
        "allowed_worker_ids": ["worker-compute-a", "worker-compute-b"],
        "required_roles": ["compute"],
        "priority": "normal",
        "task": {
            "kind": "compute",
            "payload": "web-a",
            "transport": "web",
        },
    },
    {
        "task_id": "web-compute-b",
        "submit": "web",
        "allowed_worker_ids": ["worker-compute-a", "worker-compute-b"],
        "required_roles": ["compute"],
        "priority": "normal",
        "task": {
            "kind": "compute",
            "payload": "web-b",
            "transport": "web",
        },
    },
    {
        "task_id": "rpc-verify-a",
        "submit": "rpc",
        "allowed_worker_ids": ["worker-verify-a", "worker-verify-b"],
        "required_roles": ["verify"],
        "priority": "normal",
        "task": {
            "kind": "verify",
            "payload": "rpc-a",
            "transport": "rpc",
        },
    },
    {
        "task_id": "rpc-verify-b",
        "submit": "rpc",
        "allowed_worker_ids": ["worker-verify-a", "worker-verify-b"],
        "required_roles": ["verify"],
        "priority": "normal",
        "task": {
            "kind": "verify",
            "payload": "rpc-b",
            "transport": "rpc",
        },
    },
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _http_json(url: str, payload: dict[str, Any], *, timeout_s: float = 10.0) -> dict[str, Any]:
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_manifest(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return [dict(item) for item in DEFAULT_TASKS]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("manifest_not_list")
    tasks: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("manifest_item_not_object")
        tasks.append(dict(item))
    return tasks


def _normalize_task_spec(item: dict[str, Any]) -> dict[str, Any]:
    required = ("task_id", "submit", "allowed_worker_ids", "required_roles", "task")
    for key in required:
        if key not in item:
            raise ValueError(f"missing_{key}")
    task_id = str(item["task_id"]).strip()
    if not task_id:
        raise ValueError("missing_task_id")
    submit = str(item["submit"]).strip().lower()
    if submit not in {"web", "rpc"}:
        raise ValueError("unsupported_submit_transport")
    allowed_worker_ids = [str(item_id).strip() for item_id in item["allowed_worker_ids"] if str(item_id).strip()]
    if not allowed_worker_ids:
        raise ValueError("empty_allowed_worker_ids")
    required_roles = [str(role).strip().lower() for role in item["required_roles"] if str(role).strip()]
    if not required_roles:
        raise ValueError("empty_required_roles")
    task = item["task"]
    if not isinstance(task, dict):
        raise ValueError("task_not_object")
    payload = dict(item)
    payload["task_id"] = task_id
    payload["submit"] = submit
    payload["allowed_worker_ids"] = allowed_worker_ids
    payload["required_roles"] = required_roles
    payload["priority"] = str(payload.get("priority", "normal")).strip().lower()
    payload["task"] = task
    return payload


def _submit_web(web_url: str, spec: dict[str, Any]) -> dict[str, Any]:
    response = _http_json(
        web_url,
        {
            "name": "tools.silicium.submit_task",
            "args": {
                "task_id": spec["task_id"],
                "task": spec["task"],
                "required_roles": spec["required_roles"],
                "priority": spec["priority"],
            },
        },
    )
    if response.get("ok") is not True:
        raise AssertionError(response)
    result = response.get("result", {})
    if not isinstance(result, dict):
        raise AssertionError(response)
    if result.get("status") != "queued":
        raise AssertionError(response)
    if result.get("task_id") != spec["task_id"]:
        raise AssertionError(response)
    if result.get("required_roles") != spec["required_roles"]:
        raise AssertionError(response)
    if result.get("priority") != spec["priority"]:
        raise AssertionError(response)
    resource = str(result.get("resource", ""))
    if not resource.startswith("resources://silicium/tasks/by-id/"):
        raise AssertionError(response)
    queue_path = str(result.get("queue", ""))
    if not queue_path.endswith("tasks.queue.ndjson"):
        raise AssertionError(response)
    return response


def _submit_rpc(rpc_url: str, spec: dict[str, Any]) -> dict[str, Any]:
    response = RpcClient(rpc_url, "", timeout_ms=5000).call(
        "task.dispatch",
        {
            "task_id": spec["task_id"],
            "required_roles": spec["required_roles"],
            "priority": spec["priority"],
            "task": spec["task"],
        },
    )
    if not isinstance(response, dict):
        raise AssertionError(response)
    if response.get("status") != "dispatched":
        raise AssertionError(response)
    if response.get("task_id") != spec["task_id"]:
        raise AssertionError(response)
    return response


def _load_queue_entries(data_dir: Path, role: str) -> list[dict[str, Any]]:
    queue_path = data_dir / f"tasks.{role}.queue.ndjson"
    if not queue_path.exists():
        raise AssertionError(f"missing queue file: {queue_path}")
    entries: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _wait_for_results(data_dir: Path, specs: list[dict[str, Any]], *, timeout_s: float) -> dict[str, dict[str, Any]]:
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    result_paths = {spec["task_id"]: data_dir / f"result.{spec['task_id']}.json" for spec in specs}
    while True:
        remaining = [task_id for task_id, path in result_paths.items() if not path.exists()]
        if not remaining:
            break
        if time.monotonic() > deadline:
            raise TimeoutError(f"missing results: {remaining}")
        time.sleep(0.25)

    reports: dict[str, dict[str, Any]] = {}
    used_workers_by_role: dict[str, set[str]] = {}
    for spec in specs:
        task_id = spec["task_id"]
        result = _read_json(result_paths[task_id])
        task = _read_json(data_dir / "tasks" / f"{task_id}.json")
        queue_entries = _load_queue_entries(data_dir, spec["required_roles"][0])
        queue_entry = next((entry for entry in queue_entries if str(entry.get("task_id", "")) == task_id), None)
        if queue_entry is None:
            raise AssertionError(f"queue entry not found for {task_id}")

        assert queue_entry.get("status") == "queued", queue_entry
        assert queue_entry.get("envelope_kind") == "task", queue_entry
        assert queue_entry.get("task", {}).get("transport") == spec["task"]["transport"], queue_entry
        assert queue_entry.get("priority") == spec["priority"], queue_entry

        assert task["task_id"] == task_id, task
        assert task["envelope_kind"] == "task", task
        assert task["status"] == "completed", task
        assert task["handled_by"] in spec["allowed_worker_ids"], task
        assert task["worker_role"] == spec["required_roles"][0], task
        assert task["priority"] == spec["priority"], task
        assert task["priority_rank"] == 50, task
        assert task["required_roles"] == spec["required_roles"], task
        assert task["task"]["payload"] == spec["task"]["payload"], task
        assert task["submitted_utc"], task
        assert task["completed_utc"], task

        assert result["success"] is True, result
        assert result["task_id"] == task_id, result
        assert result["handled_by"] in spec["allowed_worker_ids"], result
        assert result["worker_role"] == spec["required_roles"][0], result
        expected_transport = str(spec.get("expected_transport", "")).strip()
        if expected_transport:
            assert result["transport"] == expected_transport, result
        assert result["task"]["payload"] == spec["task"]["payload"], result

        role = spec["required_roles"][0]
        used_workers_by_role.setdefault(role, set()).add(str(result["handled_by"]))
        reports[task_id] = {"task": task, "result": result, "queue": queue_entry}

    events_path = data_dir / "rpc.events.ndjson"
    if not events_path.exists():
        raise AssertionError(f"missing rpc events file: {events_path}")
    event_lines = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_task_ids = {str(event.get("item_id", "")) for event in event_lines if isinstance(event, dict) and event.get("event") == "task.queued"}
    for spec in specs:
        if spec["submit"] == "rpc" and spec["task_id"] not in event_task_ids:
            raise AssertionError(f"missing rpc queued event for {spec['task_id']}")

    expected_role_workers = {
        "compute": {"worker-compute-a", "worker-compute-b"},
        "verify": {"worker-verify-a", "worker-verify-b"},
    }
    for role, expected_workers in expected_role_workers.items():
        observed = used_workers_by_role.get(role, set())
        if observed != expected_workers:
            raise AssertionError(f"unexpected workers for {role}: {sorted(observed)}")

    return reports


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the mixed RPC/web Silicium e2e scenario.")
    parser.add_argument("--web-url", required=True)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--data-dir", required=True, help="Directory holding queues, tasks, results, and events.")
    parser.add_argument("--manifest", default="", help="Optional JSON manifest describing the tasks to submit.")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--submit-timeout-s", type=float, default=10.0)
    parser.add_argument("--task-prefix", default="", help="Optional prefix applied to every task_id to avoid stale collisions.")
    parser.add_argument("--expected-transport", default="", help="Optional transport label expected in worker results.")
    parser.add_argument("--report", default="", help="Optional path to write the validation report.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest) if str(args.manifest).strip() else None
    specs = [_normalize_task_spec(item) for item in _load_manifest(manifest_path)]
    if not specs:
        raise SystemExit("empty manifest")
    task_prefix = str(args.task_prefix).strip()
    for spec in specs:
        if task_prefix:
            spec["task_id"] = f"{task_prefix}-{spec['task_id']}"
        spec["expected_transport"] = str(spec.get("expected_transport", args.expected_transport)).strip()

    submitters = []
    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        for spec in specs:
            if spec["submit"] == "web":
                submitters.append(pool.submit(_submit_web, args.web_url, spec))
            else:
                submitters.append(pool.submit(_submit_rpc, args.rpc_url, spec))
        for future in as_completed(submitters):
            future.result(timeout=max(1.0, float(args.submit_timeout_s)))

    reports = _wait_for_results(data_dir, specs, timeout_s=float(args.timeout_s))
    payload = {
        "ok": True,
        "data_dir": str(data_dir),
        "tasks": reports,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if args.report:
        _write_json(Path(args.report), payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
