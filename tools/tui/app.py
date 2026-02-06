from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    LoadingIndicator,
    OptionList,
    ProgressBar,
    RichLog,
    Static,
)
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


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class SiliciumTui(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #left {
        width: 38%;
        min-width: 32;
        padding: 1 1;
    }

    #right {
        width: 62%;
        padding: 1 1;
    }

    #actions {
        height: 1fr;
        border: round $secondary;
    }

    #taskbar {
        height: 3;
        padding: 0 1;
        border: round $primary;
        align: left middle;
        background: $panel;
    }

    #taskbar-left {
        width: 1fr;
        align: left middle;
    }

    #taskbar-right {
        width: auto;
        align: right middle;
    }

    #taskbar-buttons Button {
        margin: 0 1;
        background: transparent;
        border: none;
        color: $accent;
        padding: 0 0;
    }

    #taskbar-buttons Button:hover {
        color: $text;
        text-style: bold;
    }

    #taskbar-buttons Button:focus {
        color: $text;
        text-style: bold;
    }

    #run.run-ready {
        text-style: bold;
        background: $primary;
        color: $background;
    }

    .taskbar-sep {
        color: $text-muted;
    }

    #actions-title,
    #status-title,
    #log-title {
        text-style: bold;
        color: $accent;
        padding: 0 1;
    }

    #taskbar-title {
        text-style: bold;
        margin-right: 1;
    }

    #taskbar-state {
        color: $text-muted;
    }

    #details {
        height: 6;
        border: round $primary;
        padding: 1 1;
        color: $text-muted;
    }

    #status-panel {
        height: 9;
        border: round $secondary;
        padding: 1 1;
    }

    #status-head {
        text-style: bold;
        height: 1;
    }

    #status-badges {
        height: 2;
        align: left middle;
    }

    .badge {
        padding: 0 1;
        margin-right: 1;
        background: $panel;
        color: $text;
        text-style: bold;
    }

    .badge--running {
        background: $success;
        color: $background;
    }

    .badge--error {
        background: $error;
        color: $background;
    }

    #status-row {
        height: 2;
        align: left middle;
    }

    #status-lines {
        height: 1fr;
    }

    #progress {
        width: 28;
        margin-left: 2;
    }

    #log {
        height: 1fr;
        border: round $secondary;
    }

    #hint {
        height: 3;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("l", "clear_log", "Clear log"),
        ("i", "stop", "Interrupt"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._actions: list[ActionSpec] = build_actions()
        self._action_by_key = {action.key: action for action in self._actions}
        self._action_running = False
        self._progress_value = 0
        self._progress_timer = None
        self._elapsed_timer = None
        self._log_path: Path | None = None
        self._action_start_time: float | None = None
        self._current_action: ActionSpec | None = None
        self._selected_action: ActionSpec | None = None
        self._exit_code: int | None = None
        self._proc: asyncio.subprocess.Process | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="taskbar"):
            with Horizontal(id="taskbar-left"):
                yield Static("Silicium TUI", id="taskbar-title")
                yield Static("Idle", id="taskbar-state")
            with Horizontal(id="taskbar-right"):
                with Horizontal(id="taskbar-buttons"):
                    yield Button("Run", id="run")
                    yield Static("│", classes="taskbar-sep")
                    yield Button("Refresh", id="refresh")
                    yield Static("│", classes="taskbar-sep")
                    yield Button("Clear log", id="clear")
                    yield Static("│", classes="taskbar-sep")
                    yield Button("Copy log", id="copy_log")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static("Actions", id="actions-title")
                yield OptionList(id="actions")
                yield Static("Click Run to start | i: interrupt | r: refresh | l: clear log | q: quit", id="hint")
                yield Static("Select an action and press Enter.", id="details")
            with Vertical(id="right"):
                yield Static("Status", id="status-title")
                with Vertical(id="status-panel"):
                    yield Static("Idle", id="status-head")
                    with Horizontal(id="status-badges"):
                        yield Static("IDLE", id="badge-state", classes="badge")
                        yield Static("EXIT -", id="badge-exit", classes="badge")
                        yield Static("ELAPSED -", id="badge-elapsed", classes="badge")
                    yield Static("-", id="status-lines")
                    with Horizontal(id="status-row"):
                        yield LoadingIndicator(id="spinner")
                        yield ProgressBar(total=100, id="progress")
                yield Static("Logs (tail)", id="log-title")
                yield RichLog(id="log", max_lines=300)
        yield Footer()

    def on_mount(self) -> None:
        option_list = self.query_one("#actions", OptionList)
        option_list.add_options(
            [Option(f"[{action.key}] {action.label}", id=action.key) for action in self._actions]
        )
        option_list.focus()
        if self._actions:
            self._selected_action = self._actions[0]
        self.query_one("#progress", ProgressBar).display = False
        self.query_one("#spinner", LoadingIndicator).display = False
        self._progress_timer = self.set_interval(0.2, self._pulse_progress, pause=True)
        self._elapsed_timer = self.set_interval(0.5, self._tick_elapsed, pause=True)
        self._render_status()
        self._sync_toolbar()

    def action_refresh(self) -> None:
        if self._action_running:
            return
        self._render_status()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_stop(self) -> None:
        if not self._action_running or not self._proc:
            return
        self._proc.terminate()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        action = self._action_by_key.get(event.option.id or "")
        if not action:
            return
        self._selected_action = action
        self.query_one("#details", Static).update(action.description)
        self._sync_toolbar()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        action = self._action_by_key.get(event.option.id or "")
        if not action:
            return
        self._selected_action = action
        self.query_one("#details", Static).update(action.description)
        self._sync_toolbar()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "run":
            self._run_selected()
        elif button_id == "refresh":
            self.action_refresh()
        elif button_id == "clear":
            self.action_clear_log()
        elif button_id == "copy_log":
            if self._log_path:
                self.set_clipboard(str(self._log_path))

    def _run_selected(self) -> None:
        if self._action_running:
            self.action_stop()
            return
        if not self._selected_action:
            return
        self.run_worker(self._execute_action(self._selected_action), exclusive=True)

    async def _execute_action(self, action: ActionSpec) -> None:
        if self._action_running:
            return
        self._action_running = True
        self._current_action = action
        self._exit_code = None
        self._action_start_time = asyncio.get_running_loop().time()
        self._progress_value = 0

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = LOG_DIR / f"{timestamp}_{action.key}.log"

        progress = self.query_one("#progress", ProgressBar)
        spinner = self.query_one("#spinner", LoadingIndicator)
        progress.display = True
        spinner.display = True
        progress.update(progress=0)
        if self._progress_timer:
            self._progress_timer.resume()
        if self._elapsed_timer:
            self._elapsed_timer.resume()

        log = self.query_one("#log", RichLog)
        log.clear()
        command = action.command()
        command_line = f"$ {' '.join(command)}"
        log.write(command_line, scroll_end=True)

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=REPO_ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:  # pragma: no cover - UI error path
            log.write(f"[error] Failed to start command: {exc}", scroll_end=True)
            self._exit_code = 1
            self._action_running = False
            progress.display = False
            spinner.display = False
            if self._progress_timer:
                self._progress_timer.pause()
            if self._elapsed_timer:
                self._elapsed_timer.pause()
            self._render_status()
            self._sync_toolbar()
            return

        self._proc = proc

        with self._log_path.open("w", encoding="utf-8") as handle:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text_line = line.decode(errors="replace").rstrip()
                handle.write(text_line + "\n")
                log.write(text_line, scroll_end=True)

            await proc.wait()

        self._exit_code = proc.returncode
        self._action_running = False
        self._proc = None
        progress.update(progress=100)
        progress.display = False
        spinner.display = False
        if self._progress_timer:
            self._progress_timer.pause()
        if self._elapsed_timer:
            self._elapsed_timer.pause()
        self._render_status()
        self._sync_toolbar()

    def _render_status(self) -> None:
        status_head = self.query_one("#status-head", Static)
        status_lines = self.query_one("#status-lines", Static)
        badge_state = self.query_one("#badge-state", Static)
        badge_exit = self.query_one("#badge-exit", Static)
        badge_elapsed = self.query_one("#badge-elapsed", Static)
        action_label = self._current_action.label if self._current_action else "-"
        command = " ".join(self._current_action.command()) if self._current_action else "-"
        log_path = str(self._log_path) if self._log_path else "-"
        elapsed = None
        start_time = self._action_start_time
        if isinstance(start_time, (int, float)):
            elapsed = asyncio.get_running_loop().time() - start_time
        exit_code = "-"
        if self._exit_code is not None:
            exit_code = str(self._exit_code)
        state = "Running" if self._action_running else "Idle"
        status_head.update(action_label)
        status_lines.update("\n".join([f"Command: {command}", f"Log    : {log_path}"]))
        badge_state.update(state.upper())
        badge_state.set_class(state == "Running", "badge--running")
        badge_exit.update(f"EXIT {exit_code}")
        badge_exit.set_class(self._exit_code not in (None, 0, "0"), "badge--error")
        badge_elapsed.update(f"ELAPSED {format_duration(elapsed)}")
        self.query_one("#taskbar-state", Static).update(f"• {state}")

    def _sync_toolbar(self) -> None:
        run_button = self.query_one("#run", Button)
        copy_button = self.query_one("#copy_log", Button)
        run_button.label = "Interrupt" if self._action_running else "Run"
        run_button.variant = "error" if self._action_running else "primary"
        run_button.set_class(
            bool(self._selected_action) and not self._action_running, "run-ready"
        )
        run_button.disabled = self._selected_action is None
        copy_button.disabled = self._log_path is None

    def _tick_elapsed(self) -> None:
        if not self._action_running:
            return
        self._render_status()

    def _pulse_progress(self) -> None:
        if not self._action_running:
            return
        progress = self.query_one("#progress", ProgressBar)
        self._progress_value = (self._progress_value + 3) % 101
        progress.update(progress=self._progress_value)


def run() -> None:
    SiliciumTui().run()
