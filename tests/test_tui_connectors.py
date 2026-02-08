from __future__ import annotations

from tools.tui.actions import ActionSpec
from tools.tui.connectors import ITuiConnector, build_connector_registry
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
    assert isinstance(registry["inprocess"], ITuiConnector)


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
