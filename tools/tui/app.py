from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, Static, TextLog
from textual.widgets.option_list import Option

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = [sys.executable, str(REPO_ROOT / "silicium")]


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    args: list[str]
    description: str

    def command(self) -> list[str]:
        return CLI + self.args


def build_actions() -> list[ActionSpec]:
    return [
        ActionSpec(
            key="status",
            label="Status (docker compose)",
            args=["status"],
            description="Show compose services status for the current project.",
        ),
        ActionSpec(
            key="start_localnet",
            label="Start localnet",
            args=["start", "localnet"],
            description="Start localnet validator with proxy if configured.",
        ),
        ActionSpec(
            key="stop_all",
            label="Stop all services",
            args=["stop", "all"],
            description="Stop all compose services for the project.",
        ),
        ActionSpec(
            key="logs_proxy",
            label="Logs (proxy)",
            args=["logs", "silicium-proxy"],
            description="Fetch logs for the proxy service.",
        ),
        ActionSpec(
            key="workloads",
            label="List workloads",
            args=["workload", "list"],
            description="List known workload manifests.",
        ),
        ActionSpec(
            key="check_quick",
            label="Core check (quick)",
            args=["check"],
            description="Run the quick core check flow (may use Docker/WSL).",
        ),
        ActionSpec(
            key="clean_cache",
            label="Clean cache",
            args=["clean", "cache"],
            description="Clean build caches and temporary artifacts.",
        ),
    ]


class SiliciumTui(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #left {
        width: 40%;
        min-width: 30;
        padding: 1 1;
    }

    #right {
        width: 60%;
        padding: 1 1;
    }

    #actions {
        height: 1fr;
        border: round $secondary;
    }

    #details {
        height: 6;
        border: round $primary;
        padding: 1 1;
    }

    #log {
        height: 1fr;
        border: round $secondary;
    }

    #status {
        height: 3;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("l", "clear_log", "Clear log"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._actions: list[ActionSpec] = build_actions()
        self._action_by_key = {action.key: action for action in self._actions}
        self._running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static("Actions", id="actions-title")
                yield OptionList(id="actions")
                yield Static("Select an action and press Enter.", id="details")
            with Vertical(id="right"):
                yield Static("Output", id="log-title")
                yield TextLog(id="log", highlight=False, markup=False, wrap=True)
        yield Static("Ready.", id="status")
        yield Footer()

    def on_mount(self) -> None:
        option_list = self.query_one("#actions", OptionList)
        option_list.add_options(
            [Option(f"[{action.key}] {action.label}", id=action.key) for action in self._actions]
        )
        option_list.focus()

    def action_refresh(self) -> None:
        if self._running:
            return
        self.query_one("#status", Static).update("Ready.")

    def action_clear_log(self) -> None:
        self.query_one("#log", TextLog).clear()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        action = self._action_by_key.get(event.option.id or "")
        if not action:
            return
        self.query_one("#details", Static).update(action.description)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        action = self._action_by_key.get(event.option.id or "")
        if not action:
            return
        self.run_worker(self._execute_action(action), exclusive=True)

    async def _execute_action(self, action: ActionSpec) -> None:
        if self._running:
            return
        self._running = True
        status = self.query_one("#status", Static)
        log = self.query_one("#log", TextLog)
        command = action.command()
        status.update(f"Running: {action.label}")
        log.write(f\"$ {' '.join(command)}\")
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )
        if result.stdout:
            log.write(result.stdout.rstrip())
        if result.stderr:
            log.write(result.stderr.rstrip())
        status.update(f"Done: {action.label} (exit {result.returncode})")
        self._running = False


def run() -> None:
    SiliciumTui().run()
