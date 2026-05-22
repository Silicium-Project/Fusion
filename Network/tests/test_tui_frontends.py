from __future__ import annotations

from pathlib import Path

from tools.tui.frontends import (
    FrontendRunConfig,
    HeadlessFrontend,
    ITuiFrontend,
    build_frontend_registry,
)
from tools.tui.connectors import ITuiConnector


def test_frontend_registry_exposes_all_adapters() -> None:
    registry = build_frontend_registry()
    assert {"textual", "curses", "headless"}.issubset(registry.keys())
    for adapter in registry.values():
        assert isinstance(adapter, ITuiFrontend)


def test_headless_frontend_returns_shell_fallback_without_script() -> None:
    frontend = HeadlessFrontend()
    result = frontend.run(FrontendRunConfig())
    assert result.ok
    assert result.fallback_to_shell


def test_headless_frontend_script_failure_detection(tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text("{\"steps\": []}", encoding="utf-8")

    def fake_runner(*_args, **_kwargs):
        return {
            "records": {
                "status": {"status": "failed"},
            }
        }

    frontend = HeadlessFrontend(script_runner=fake_runner)
    result = frontend.run(FrontendRunConfig(headless_script=script))
    assert not result.ok
    assert "failed actions" in result.reason


def test_headless_frontend_passes_connector_to_script_runner(tmp_path: Path) -> None:
    class FakeConnector(ITuiConnector):
        def __init__(self) -> None:
            super().__init__("fake")

        def run_action(self, action, runner_mode, log_path, cancel_event) -> int:  # pragma: no cover - not called here
            return 0

    connector = FakeConnector()
    script = tmp_path / "script.json"
    script.write_text("{\"steps\": []}", encoding="utf-8")
    captured = {}

    def fake_runner(script_path, **kwargs):
        captured["script_path"] = script_path
        captured["connector"] = kwargs.get("connector")
        return {"records": {}}

    frontend = HeadlessFrontend(script_runner=fake_runner)
    result = frontend.run(
        FrontendRunConfig(
            headless_script=script,
            connector=connector,
        )
    )
    assert result.ok
    assert captured["script_path"] == script
    assert captured["connector"] is connector
