from __future__ import annotations

import sys
import threading
from pathlib import Path

from tools.tui.actions import ActionSpec
from tools.tui.connectors import ITuiConnector, StdIoConnector, build_connector_registry
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
    assert isinstance(registry["inprocess"], ITuiConnector)
    assert isinstance(registry["stdio"], ITuiConnector)


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
