from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from tools.dev.tui.headless_app import run_script as default_headless_script_runner

if TYPE_CHECKING:
    from tools.dev.tui.connectors import ITuiConnector


@dataclass(frozen=True)
class FrontendRunConfig:
    headless_script: Path | None = None
    headless_timeout: float = 120.0
    headless_json: Path | None = None
    connector: "ITuiConnector | None" = None


HeadlessScriptRunner = Callable[..., dict[str, object]]
TextualProbe = Callable[[], tuple[bool, str]]
TextualRun = Callable[[FrontendRunConfig], None]


@dataclass(frozen=True)
class FrontendRunResult:
    ok: bool
    reason: str = ""
    fallback_to_shell: bool = False


class ITuiFrontend(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def probe(self) -> tuple[bool, str]:
        pass

    @abstractmethod
    def run(self, config: FrontendRunConfig) -> FrontendRunResult:
        pass


class TextualFrontend(ITuiFrontend):
    def __init__(
        self,
        *,
        probe_impl: TextualProbe | None = None,
        run_impl: TextualRun | None = None,
    ) -> None:
        super().__init__("textual")
        self._probe_impl = probe_impl or _default_textual_probe
        self._run_impl = run_impl or _default_textual_run

    def probe(self) -> tuple[bool, str]:
        return self._probe_impl()

    def run(self, config: FrontendRunConfig) -> FrontendRunResult:
        ok, reason = self.probe()
        if not ok:
            return FrontendRunResult(False, reason)
        try:
            _invoke_textual_run(self._run_impl, config)
            return FrontendRunResult(True, "")
        except Exception as exc:  # pragma: no cover - interactive path
            return FrontendRunResult(False, f"textual frontend failed: {exc}")


class CursesFrontend(ITuiFrontend):
    def __init__(self) -> None:
        super().__init__("curses")

    def probe(self) -> tuple[bool, str]:
        try:
            from tools.dev.tui.curses_app import _load_curses  # type: ignore[attr-defined]
        except ImportError:
            return False, "curses frontend module unavailable."
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"failed to import curses frontend: {exc}"
        try:
            _load_curses()
            return True, ""
        except RuntimeError as exc:
            return False, str(exc)
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"curses probe failed: {exc}"

    def run(self, config: FrontendRunConfig) -> FrontendRunResult:
        ok, reason = self.probe()
        if not ok:
            return FrontendRunResult(False, reason)
        from tools.dev.tui.curses_app import run as run_curses

        try:
            run_curses()
            return FrontendRunResult(True, "")
        except RuntimeError as exc:
            return FrontendRunResult(False, str(exc))
        except Exception as exc:  # pragma: no cover - interactive path
            return FrontendRunResult(False, f"curses frontend failed: {exc}")


class HeadlessFrontend(ITuiFrontend):
    def __init__(self, *, script_runner: HeadlessScriptRunner = default_headless_script_runner) -> None:
        super().__init__("headless")
        self._script_runner = script_runner

    def probe(self) -> tuple[bool, str]:
        return True, ""

    def run(self, config: FrontendRunConfig) -> FrontendRunResult:
        if config.headless_script is None:
            return FrontendRunResult(True, fallback_to_shell=True)

        script_path = config.headless_script
        if not script_path.exists():
            return FrontendRunResult(False, f"Headless script not found: {script_path}")

        snapshot = self._script_runner(
            script_path,
            timeout_sec=config.headless_timeout,
            connector=config.connector,
        )
        if config.headless_json:
            config.headless_json.parent.mkdir(parents=True, exist_ok=True)
            config.headless_json.write_text(
                json.dumps(snapshot, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        records = snapshot.get("records", {})
        failed = [
            key
            for key, rec in records.items()
            if rec.get("status") not in {"completed", "interrupted"}
        ]
        if failed:
            return FrontendRunResult(
                False,
                f"headless script failed actions: {', '.join(sorted(failed))}",
            )
        return FrontendRunResult(True, "Headless script: OK")


def build_frontend_registry() -> dict[str, ITuiFrontend]:
    return {
        "textual": TextualFrontend(),
        "curses": CursesFrontend(),
        "headless": HeadlessFrontend(),
    }


def _default_textual_probe() -> tuple[bool, str]:
    try:
        from tools.dev.tui.app import run as _run_textual  # noqa: F401
    except ImportError:
        return False, "Textual dependencies missing."
    return True, ""


def _default_textual_run(config: FrontendRunConfig) -> None:
    from tools.dev.tui.app import run as run_textual

    run_textual(connector=config.connector)


def _invoke_textual_run(run_impl: TextualRun, config: FrontendRunConfig) -> None:
    try:
        signature = inspect.signature(run_impl)
    except (TypeError, ValueError):
        run_impl(config)
        return

    positional = [
        param
        for param in signature.parameters.values()
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not positional:
        run_impl()  # type: ignore[call-arg]
        return
    run_impl(config)
