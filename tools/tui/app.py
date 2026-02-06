from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Iterable

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, OptionList, ProgressBar, Static, TextLog
from textual.widgets.option_list import Option

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = [sys.executable, str(REPO_ROOT / "silicium")]
LOG_DIR = REPO_ROOT / ".silicium" / "logs"


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
        align: left middle;
    }

    #status-text {
        width: 1fr;
    }

    #progress {
        width: 30;
        margin-left: 2;
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
        self._progress_value = 0
        self._progress_timer = None
        self._log_buffer: deque[str] = deque(maxlen=200)
        self._log_path: Path | None = None

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
        with Horizontal(id="status"):
            yield Static("Ready.", id="status-text")
            yield ProgressBar(total=100, id="progress")
        yield Footer()

    def on_mount(self) -> None:
        option_list = self.query_one("#actions", OptionList)
        option_list.add_options(
            [Option(f"[{action.key}] {action.label}", id=action.key) for action in self._actions]
        )
        option_list.focus()
        progress = self.query_one("#progress", ProgressBar)
        progress.display = False
        self._progress_timer = self.set_interval(0.2, self._pulse_progress, pause=True)

    def action_refresh(self) -> None:
        if self._running:
            return
        self.query_one("#status-text", Static).update("Ready.")

    def action_clear_log(self) -> None:
        self.query_one("#log", TextLog).clear()
        self._log_buffer.clear()

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
        status = self.query_one("#status-text", Static)
        log = self.query_one("#log", TextLog)
        progress = self.query_one("#progress", ProgressBar)
        command = action.command()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = LOG_DIR / f"{timestamp}_{action.key}.log"
        status.update(f"Running: {action.label} (log: {self._log_path})")
        progress.display = True
        progress.update(progress=0)
        if self._progress_timer:
            self._progress_timer.resume()

        log.clear()
        self._log_buffer.clear()
        log.write(f"$ {' '.join(command)}")
        self._log_buffer.append(f"$ {' '.join(command)}")

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=REPO_ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        loop = asyncio.get_running_loop()
        last_flush = loop.time()
        flush_interval = 0.3

        with self._log_path.open("w", encoding="utf-8") as handle:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text_line = line.decode(errors="replace").rstrip()
                handle.write(text_line + "\n")
                self._log_buffer.append(text_line)
                now = loop.time()
                if now - last_flush >= flush_interval:
                    log.clear()
                    for entry in self._log_buffer:
                        log.write(entry)
                    last_flush = now

            await proc.wait()

        if self._log_buffer:
            log.clear()
            for entry in self._log_buffer:
                log.write(entry)

        status.update(f"Done: {action.label} (exit {proc.returncode})")
        progress.update(progress=100)
        progress.display = False
        if self._progress_timer:
            self._progress_timer.pause()
        self._running = False

    def _pulse_progress(self) -> None:
        if not self._running:
            return
        progress = self.query_one("#progress", ProgressBar)
        self._progress_value = (self._progress_value + 3) % 101
        progress.update(progress=self._progress_value)


def run() -> None:
    SiliciumTui().run()
