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

    specs = [
        {
            "task_id": "submit-web-a",
            "submit": "web",
            "allowed_worker_ids": ["worker-compute-a", "worker-compute-b"],
            "required_roles": ["compute"],
            "priority": "normal",
            "expected_transport": "vps-compose",
            "task": {"kind": "compute", "payload": "web-a", "transport": "web"},
        },
        {
            "task_id": "submit-web-b",
            "submit": "web",
            "allowed_worker_ids": ["worker-compute-a", "worker-compute-b"],
            "required_roles": ["compute"],
            "priority": "normal",
            "expected_transport": "vps-compose",
            "task": {"kind": "compute", "payload": "web-b", "transport": "web"},
        },
        {
            "task_id": "submit-rpc-a",
            "submit": "rpc",
            "allowed_worker_ids": ["worker-verify-a", "worker-verify-b"],
            "required_roles": ["verify"],
            "priority": "normal",
            "expected_transport": "vps-compose",
            "task": {"kind": "verify", "payload": "rpc-a", "transport": "rpc"},
        },
        {
            "task_id": "submit-rpc-b",
            "submit": "rpc",
            "allowed_worker_ids": ["worker-verify-a", "worker-verify-b"],
            "required_roles": ["verify"],
            "priority": "normal",
            "expected_transport": "vps-compose",
            "task": {"kind": "verify", "payload": "rpc-b", "transport": "rpc"},
        },
    ]

    runtime_rows = [
        ("compute", "worker-compute-a", "runtime-compute-001", "web-a"),
        ("compute", "worker-compute-b", "runtime-compute-002", "web-b"),
        ("verify", "worker-verify-a", "runtime-verify-001", "rpc-a"),
        ("verify", "worker-verify-b", "runtime-verify-002", "rpc-b"),
    ]

    for role, worker_id, runtime_task_id, payload in runtime_rows:
        submit_transport = "web" if payload.startswith("web-") else "rpc"
        queue_path = data_dir / f"tasks.{role}.queue.ndjson"
        with queue_path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "task_id": runtime_task_id,
                        "status": "queued",
                        "envelope_kind": "task",
                        "priority": "normal",
                        "task": {"payload": payload, "transport": submit_transport},
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
            "task": {"payload": payload, "transport": submit_transport},
        }
        (tasks_dir / f"{runtime_task_id}.json").write_text(json.dumps(task_payload), encoding="utf-8")
        result_payload = {
            "success": True,
            "task_id": runtime_task_id,
            "handled_by": worker_id,
            "worker_role": role,
            "transport": "vps-compose",
            "task": {"payload": payload, "transport": submit_transport},
        }
        (data_dir / f"result.{runtime_task_id}.json").write_text(json.dumps(result_payload), encoding="utf-8")

    events = [
        {"event": "task.queued", "item_id": "submit-web-a"},
        {"event": "task.queued", "item_id": "submit-web-b"},
        {"event": "task.queued", "item_id": "submit-rpc-a"},
        {"event": "task.queued", "item_id": "submit-rpc-b"},
    ]
    (data_dir / "rpc.events.ndjson").write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")

    reports, worker_counts = e2e_scenario._wait_for_results(data_dir, specs, timeout_s=1.0)

    assert set(reports) == {spec["task_id"] for spec in specs}
    assert reports["submit-web-a"]["result"]["handled_by"] == "worker-compute-a"
    assert reports["submit-web-b"]["result"]["handled_by"] == "worker-compute-b"
    assert reports["submit-rpc-a"]["result"]["handled_by"] == "worker-verify-a"
    assert reports["submit-rpc-b"]["result"]["handled_by"] == "worker-verify-b"
    assert reports["submit-web-a"]["result"]["transport"] == "vps-compose"
    assert reports["submit-rpc-b"]["result"]["transport"] == "vps-compose"
    assert worker_counts["compute"]["worker-compute-a"] == 1
    assert worker_counts["compute"]["worker-compute-b"] == 1
    assert worker_counts["verify"]["worker-verify-a"] == 1
    assert worker_counts["verify"]["worker-verify-b"] == 1
