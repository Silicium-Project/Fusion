"""Unit tests of ``McpTaskStore`` queue ingress failure handling (no server)."""

import json
from pathlib import Path
from typing import Any

from tools.mcp_server import McpTaskStore


def test_task_submit_marks_registry_entry_failed_when_canonical_queue_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    export_dir = tmp_path / "mcp"
    store = McpTaskStore(export_dir)
    queue_path = export_dir / "tasks.queue.ndjson"
    original_open = Path.open

    def open_with_denied_queue(path: Path, *args: Any, **kwargs: Any):
        if path == queue_path:
            raise PermissionError(13, "Permission denied", str(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_with_denied_queue)
    try:
        store.submit({"task_id": "permission-test", "task": {"kind": "compute"}})
    except PermissionError:
        pass
    else:
        raise AssertionError("submission unexpectedly succeeded")

    registry_entry = json.loads(
        (export_dir / "tasks" / "permission-test.json").read_text(encoding="utf-8")
    )
    assert registry_entry["status"] == "failed"
    assert registry_entry["error_type"] == "PermissionError"
    assert "queue_ingress_failed" in registry_entry["error"]


def test_task_submit_succeeds_when_only_role_queue_fails(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    export_dir = tmp_path / "mcp"
    store = McpTaskStore(export_dir)
    role_queue_path = export_dir / "tasks.compute.queue.ndjson"
    original_open = Path.open

    def open_with_denied_role_queue(path: Path, *args: Any, **kwargs: Any):
        if path == role_queue_path:
            raise PermissionError(13, "Permission denied", str(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_with_denied_role_queue)
    result = store.submit({"task_id": "role-queue-test", "task": {"kind": "compute"}})

    assert result["status"] == "queued"
    assert (export_dir / "tasks" / "role-queue-test.json").exists()
    assert "role-queue-test" in (export_dir / "tasks.queue.ndjson").read_text(encoding="utf-8")
