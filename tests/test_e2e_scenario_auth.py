from __future__ import annotations

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
