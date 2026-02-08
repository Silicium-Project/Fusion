from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
import sys
import threading
from pathlib import Path
from urllib import parse as url_parse

from tools.tui.actions import ActionSpec
from tools.tui.connectors import HttpConnector, ITuiConnector, StdIoConnector, build_connector_registry
from tools.tui.headless_app import run_script


def _action(key: str) -> ActionSpec:
    return ActionSpec(
        key=key,
        label=key,
        args=["status"],
        description=f"action {key}",
    )


def test_connector_registry_defaults_to_inprocess() -> None:
    registry = build_connector_registry()
    assert "inprocess" in registry
    assert "stdio" in registry
    assert "http" in registry
    assert isinstance(registry["inprocess"], ITuiConnector)
    assert isinstance(registry["stdio"], ITuiConnector)
    assert isinstance(registry["http"], ITuiConnector)


def test_headless_script_uses_selected_connector(tmp_path: Path) -> None:
    class FakeConnector(ITuiConnector):
        def __init__(self) -> None:
            super().__init__("fake")
            self.calls = 0

        def run_action(self, action, runner_mode, log_path, cancel_event) -> int:
            self.calls += 1
            log_path.write_text(f"{action.key}:{runner_mode}\n", encoding="utf-8")
            return 0

    connector = FakeConnector()
    script = tmp_path / "script.json"
    script.write_text(
        "{\"steps\":[{\"run\":\"a\"},{\"wait_all\":true,\"timeout_sec\":5}]}",
        encoding="utf-8",
    )

    snapshot = run_script(
        script,
        actions=[_action("a")],
        log_dir=tmp_path,
        connector=connector,
    )
    assert connector.calls == 1
    assert snapshot["records"]["a"]["status"] == "completed"


def test_stdio_connector_reads_json_events(tmp_path: Path) -> None:
    fake_core = tmp_path / "fake_core.py"
    fake_core.write_text(
        "\n".join(
            [
                "import base64",
                "import json",
                "import sys",
                "line = sys.stdin.readline()",
                "payload = json.loads(line)",
                "cmd = base64.b64decode(payload['command_b64']).decode('utf-8')",
                "print(json.dumps({'type': 'log', 'line': 'cmd:' + cmd}), flush=True)",
                "print(json.dumps({'type': 'state', 'status': 'completed', 'exit_code': 0}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    connector = StdIoConnector(core_command=[sys.executable, str(fake_core)])
    log_path = tmp_path / "stdio.log"

    code = connector.run_action(_action("a"), "auto", log_path, threading.Event())
    assert code == 0
    content = log_path.read_text(encoding="utf-8")
    assert "cmd:" in content


def test_stdio_connector_uses_state_exit_code(tmp_path: Path) -> None:
    fake_core = tmp_path / "fake_core_fail.py"
    fake_core.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "_ = sys.stdin.readline()",
                "print(json.dumps({'type': 'state', 'status': 'failed', 'exit_code': 7}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    connector = StdIoConnector(core_command=[sys.executable, str(fake_core)])
    log_path = tmp_path / "stdio_fail.log"

    code = connector.run_action(_action("a"), "auto", log_path, threading.Event())
    assert code == 7


class _HttpCoreState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_run_id = 1
        self._runs: dict[str, dict[str, object]] = {}

    def start_run(self, command: list[str]) -> str:
        with self._lock:
            run_id = str(self._next_run_id)
            self._next_run_id += 1
            self._runs[run_id] = {
                "status": "running",
                "exit_code": None,
                "lines": [],
                "cursor": 0,
                "command": command,
                "interrupt": False,
            }
        t = threading.Thread(target=self._run_thread, args=(run_id,), daemon=True)
        t.start()
        return run_id

    def interrupt(self, run_id: str) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id]["interrupt"] = True

    def state(self, run_id: str) -> dict[str, object]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return {"status": "error", "exit_code": 1}
            exit_code = run.get("exit_code")
            payload: dict[str, object] = {"status": run["status"]}
            if isinstance(exit_code, int):
                payload["exit_code"] = exit_code
            return payload

    def logs(self, run_id: str, cursor: int) -> dict[str, object]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return {"lines": [], "next_cursor": cursor}
            lines = run["lines"]
            next_cursor = int(run["cursor"])
            sliced = []
            for idx in range(cursor, len(lines)):
                sliced.append({"cursor": idx + 1, "line": lines[idx]})
            return {"lines": sliced, "next_cursor": next_cursor}

    def _run_thread(self, run_id: str) -> None:
        with self._lock:
            command = list(self._runs[run_id]["command"])  # type: ignore[list-item]
        self._append(run_id, "start:" + " ".join(command))
        time.sleep(0.05)
        with self._lock:
            interrupted = bool(self._runs[run_id]["interrupt"])
        if interrupted:
            self._append(run_id, "interrupted")
            with self._lock:
                self._runs[run_id]["status"] = "cancelled"
                self._runs[run_id]["exit_code"] = 1
                self._runs[run_id]["cursor"] = len(self._runs[run_id]["lines"])  # type: ignore[arg-type]
            return
        self._append(run_id, "done")
        with self._lock:
            self._runs[run_id]["status"] = "completed"
            self._runs[run_id]["exit_code"] = 0
            self._runs[run_id]["cursor"] = len(self._runs[run_id]["lines"])  # type: ignore[arg-type]

    def _append(self, run_id: str, line: str) -> None:
        with self._lock:
            self._runs[run_id]["lines"].append(line)  # type: ignore[union-attr]
            self._runs[run_id]["cursor"] = len(self._runs[run_id]["lines"])  # type: ignore[arg-type]


def _start_fake_http_core() -> tuple[str, ThreadingHTTPServer]:
    core = _HttpCoreState()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}

        def _send(self, payload: dict[str, object]) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/command":
                self.send_error(404)
                return
            payload = self._json()
            message_type = payload.get("type")
            if message_type == "run":
                command = payload.get("command", [])
                run_id = core.start_run(command if isinstance(command, list) else [])
                self._send({"run_id": run_id})
                return
            if message_type == "interrupt":
                run_id = str(payload.get("run_id", ""))
                core.interrupt(run_id)
                self._send({"ok": True})
                return
            self._send({"error": "unsupported"})

        def do_GET(self) -> None:  # noqa: N802
            parsed = url_parse.urlparse(self.path)
            query = url_parse.parse_qs(parsed.query)
            if parsed.path == "/state":
                run_id = (query.get("run_id") or [""])[0]
                self._send(core.state(run_id))
                return
            if parsed.path == "/logs":
                run_id = (query.get("run_id") or [""])[0]
                cursor_str = (query.get("cursor") or ["0"])[0]
                try:
                    cursor = int(cursor_str)
                except ValueError:
                    cursor = 0
                self._send(core.logs(run_id, cursor))
                return
            self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    host, port = server.server_address[:2]
    endpoint = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return endpoint, server


def test_http_connector_runs_action_and_collects_logs(tmp_path: Path) -> None:
    endpoint, server = _start_fake_http_core()
    try:
        connector = HttpConnector(endpoint)
        log_path = tmp_path / "http.log"
        code = connector.run_action(_action("status"), "auto", log_path, threading.Event())
        assert code == 0
        content = log_path.read_text(encoding="utf-8", errors="replace")
        assert "start:" in content
        assert "done" in content
    finally:
        server.shutdown()
