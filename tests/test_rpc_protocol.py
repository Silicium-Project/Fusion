from __future__ import annotations

import importlib
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_rpc_protocol_roundtrip():
    rpc_protocol = importlib.import_module("rpc_protocol")

    raw = rpc_protocol.encode_request(
        "task.dispatch",
        {"task_id": "task-1", "priority": "high"},
        "req-1",
        token="secret",
    )
    req, payload = rpc_protocol.decode_request(raw)
    assert req.request_id == "req-1"
    assert req.method == "task.dispatch"
    assert req.bearer_token == "secret"
    assert payload == {"task_id": "task-1", "priority": "high"}

    raw_resp = rpc_protocol.encode_response("req-1", True, {"ok": True}, duration_us=42)
    resp, resp_payload = rpc_protocol.decode_response(raw_resp)
    assert resp.request_id == "req-1"
    assert resp.ok is True
    assert resp.duration_us == 42
    assert resp_payload == {"ok": True}
