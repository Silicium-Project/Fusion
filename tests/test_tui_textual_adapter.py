from __future__ import annotations

from tools.dev.tui.frontends import FrontendRunConfig, TextualFrontend


def test_textual_adapter_uses_injected_run() -> None:
    called = {"run": 0}

    def probe() -> tuple[bool, str]:
        return True, ""

    def run() -> None:
        called["run"] += 1

    frontend = TextualFrontend(probe_impl=probe, run_impl=run)
    result = frontend.run(FrontendRunConfig())
    assert result.ok
    assert called["run"] == 1


def test_textual_adapter_stops_when_probe_fails() -> None:
    called = {"run": 0}

    def probe() -> tuple[bool, str]:
        return False, "missing textual"

    def run() -> None:
        called["run"] += 1

    frontend = TextualFrontend(probe_impl=probe, run_impl=run)
    result = frontend.run(FrontendRunConfig())
    assert not result.ok
    assert result.reason == "missing textual"
    assert called["run"] == 0


def test_textual_adapter_reports_run_failure() -> None:
    def probe() -> tuple[bool, str]:
        return True, ""

    def run() -> None:
        raise RuntimeError("boom")

    frontend = TextualFrontend(probe_impl=probe, run_impl=run)
    result = frontend.run(FrontendRunConfig())
    assert not result.ok
    assert "textual frontend failed: boom" in result.reason
