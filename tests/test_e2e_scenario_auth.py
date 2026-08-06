from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import e2e_scenario


def test_submit_web_attaches_bearer_token(monkeypatch):
    captured: dict[str, object] = {}

    def fake_http_json(url, payload, *, timeout_s=10.0, headers=None):
        captured["url"] = url
        captured["payload"] = payload
        captured["timeout_s"] = timeout_s
        captured["headers"] = headers
        return {
            "ok": True,
            "result": {
                "status": "queued",
                "task_id": "task-1",
                "required_roles": ["compute"],
                "priority": "normal",
                "resource": "resources://silicium/tasks/by-id/task-1",
                "queue": "/tmp/tasks.queue.ndjson",
            },
        }

    monkeypatch.setattr(e2e_scenario, "_http_json", fake_http_json)
    e2e_scenario._submit_web(
        "http://example.invalid/tools",
        {
            "task_id": "task-1",
            "task": {"kind": "compute", "payload": "x"},
            "required_roles": ["compute"],
            "priority": "normal",
        },
        auth_token="secret-token",
    )
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}


def test_submit_rpc_passes_bearer_token(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, endpoint, token="", timeout_ms=3000):
            captured["endpoint"] = endpoint
            captured["token"] = token
            captured["timeout_ms"] = timeout_ms

        def call(self, method, payload=None):
            captured["method"] = method
            captured["payload"] = payload
            return {"status": "dispatched", "task_id": "task-2"}

    monkeypatch.setattr(e2e_scenario, "RpcClient", FakeClient)
    e2e_scenario._submit_rpc(
        "tcp://127.0.0.1:9770",
        {
            "task_id": "task-2",
            "task": {"kind": "verify", "payload": "x"},
            "required_roles": ["verify"],
            "priority": "normal",
        },
        auth_token="secret-token",
    )
    assert captured["token"] == "secret-token"
    assert captured["method"] == "task.dispatch"


def test_ci_e2e_manifest_exercises_both_workers_and_submit_paths() -> None:
    manifest_path = REPO_ROOT / "ci" / "e2e-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert isinstance(manifest, list)
    assert len(manifest) == 8
    submit_modes = {str(item["submit"]) for item in manifest}
    assert submit_modes == {"web", "rpc"}
    roles = {tuple(item["required_roles"]) for item in manifest}
    assert roles == {("compute",), ("verify",)}


def test_wait_for_results_matches_runtime_generated_ids(tmp_path: Path) -> None:
    data_dir = tmp_path / "export"
    tasks_dir = data_dir / "tasks"
    tasks_dir.mkdir(parents=True)

    manifest = json.loads((REPO_ROOT / "ci" / "e2e-manifest.json").read_text(encoding="utf-8"))
    assert isinstance(manifest, list)
    assert len(manifest) == 8

    specs = []
    worker_slots = {
        "compute": ["worker-compute-a", "worker-compute-b"],
        "verify": ["worker-verify-a", "worker-verify-b"],
    }
    worker_cursors = {"compute": 0, "verify": 0}
    events: list[dict[str, object]] = []

    for item in manifest:
        assert isinstance(item, dict)
        role = str(item["required_roles"][0])
        submit = str(item["submit"])
        payload = dict(item["task"])
        submit_task_id = f"submit-{item['task_id']}"
        runtime_task_id = f"runtime-{item['task_id']}"
        worker_id = worker_slots[role][worker_cursors[role] % len(worker_slots[role])]
        worker_cursors[role] += 1
        specs.append(
            {
                "task_id": submit_task_id,
                "submit": submit,
                "allowed_worker_ids": worker_slots[role],
                "required_roles": [role],
                "priority": str(item.get("priority", "normal")),
                "expected_transport": "vps-compose",
                "task": payload,
            }
        )

        queue_path = data_dir / f"tasks.{role}.queue.ndjson"
        with queue_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "task_id": runtime_task_id,
                        "status": "queued",
                        "envelope_kind": "task",
                        "priority": "normal",
                        "task": payload,
                    }
                )
                + "\n"
            )

        task_payload = {
            "task_id": runtime_task_id,
            "envelope_kind": "task",
            "status": "completed",
            "handled_by": worker_id,
            "worker_role": role,
            "priority": "normal",
            "required_roles": [role],
            "submitted_utc": "2026-08-02T18:16:08Z",
            "completed_utc": "2026-08-02T18:16:08Z",
            "transport": "vps-compose",
            "task": payload,
        }
        (tasks_dir / f"{runtime_task_id}.json").write_text(json.dumps(task_payload), encoding="utf-8")
        result_payload = {
            "success": True,
            "task_id": runtime_task_id,
            "handled_by": worker_id,
            "worker_role": role,
            "transport": "vps-compose",
            "task": payload,
        }
        (data_dir / f"result.{runtime_task_id}.json").write_text(json.dumps(result_payload), encoding="utf-8")
        if submit == "rpc":
            events.append({"event": "task.queued", "item_id": submit_task_id})

    (data_dir / "rpc.events.ndjson").write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")

    reports, worker_counts = e2e_scenario._wait_for_results(data_dir, specs, timeout_s=1.0)

    assert set(reports) == {spec["task_id"] for spec in specs}
    assert reports["submit-web-compute-a"]["result"]["handled_by"] == "worker-compute-a"
    assert reports["submit-web-compute-b"]["result"]["handled_by"] == "worker-compute-b"
    assert reports["submit-rpc-verify-a"]["result"]["handled_by"] == "worker-verify-a"
    assert reports["submit-rpc-verify-b"]["result"]["handled_by"] == "worker-verify-b"
    assert reports["submit-web-compute-a"]["result"]["transport"] == "vps-compose"
    assert reports["submit-rpc-verify-b"]["result"]["transport"] == "vps-compose"
    assert worker_counts["compute"]["worker-compute-a"] == 2
    assert worker_counts["compute"]["worker-compute-b"] == 2
    assert worker_counts["verify"]["worker-verify-a"] == 2
    assert worker_counts["verify"]["worker-verify-b"] == 2
