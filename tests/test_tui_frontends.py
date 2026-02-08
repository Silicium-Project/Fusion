from __future__ import annotations

from pathlib import Path

from tools.tui.frontends import (
    FrontendRunConfig,
    HeadlessFrontend,
    ITuiFrontend,
    build_frontend_registry,
)


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
