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


@dataclass
class RunState:
    action: "ActionSpec"
    log_path: Path
    start_time: float
    resources: frozenset[str]
    runner_mode: str
    proc: asyncio.subprocess.Process | None
    exit_code: int | None = None


@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    args: list[str]
    description: str
    resources: frozenset[str] = frozenset()
    runner_sensitive: bool = False
    runner_resources: dict[str, frozenset[str]] | None = None

    def command(self, runner_mode: str) -> list[str]:
        cmd = CLI + self.args
        if self.runner_sensitive:
            cmd += ["--runner", runner_mode]
        return cmd

    def resources_for(self, runner_mode: str) -> set[str]:
        resources = set(self.resources)
        if self.runner_sensitive and self.runner_resources:
            resources.update(self.runner_resources.get(runner_mode, set()))
        return resources


def build_actions() -> list[ActionSpec]:
    return [
        ActionSpec(
            key="status",
            label="Status (docker compose)",
            args=["status"],
            description="Show compose services status for the current project.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="start_localnet",
            label="Start localnet",
            args=["start", "localnet"],
            description="Start localnet validator with proxy if configured.",
            resources=frozenset({"docker", "network"}),
        ),
        ActionSpec(
            key="stop_all",
            label="Stop all services",
            args=["stop", "all"],
            description="Stop all compose services for the project.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="logs_proxy",
            label="Logs (proxy)",
            args=["logs", "silicium-proxy"],
            description="Fetch logs for the proxy service.",
            resources=frozenset({"docker"}),
        ),
        ActionSpec(
            key="workloads",
            label="List workloads",
            args=["workload", "list"],
            description="List known workload manifests.",
            resources=frozenset({"io"}),
        ),
        ActionSpec(
            key="check_quick",
            label="Core check (quick)",
            args=["check"],
            description="Run the quick core check flow (may use Docker/WSL).",
            resources=frozenset({"cpu"}),
            runner_sensitive=True,
            runner_resources={
                "auto": frozenset({"docker"}),
                "docker": frozenset({"docker"}),
                "wsl": frozenset({"wsl"}),
            },
        ),
        ActionSpec(
            key="clean_cache",
            label="Clean cache",
            args=["clean", "cache"],
            description="Clean build caches and temporary artifacts.",
            resources=frozenset({"io"}),
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
        width: 32%;
        min-width: 32;
        padding: 1 1;
    }

    #right {
        width: 68%;
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
        background: $success;
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
        height: 7;
        border: round $primary;
        padding: 1 1;
        color: $text-muted;
    }

    #status-panel {
        height: 10;
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
        height: 2;
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
        self._progress_value = 0
        self._progress_timer = None
        self._elapsed_timer = None
        self._current_action: ActionSpec | None = None
        self._selected_action: ActionSpec | None = None
        self._running_actions: dict[str, RunState] = {}
        self._queued_actions: list[ActionSpec] = []
        self._active_log_action: str | None = None
        self._last_runs: dict[str, RunState] = {}
        self._runner_mode = "auto"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="taskbar"):
            with Horizontal(id="taskbar-left"):
                yield Static("Silicium TUI", id="taskbar-title")
                yield Static("Idle", id="taskbar-state")
            with Horizontal(id="taskbar-right"):
                with Horizontal(id="taskbar-buttons"):
                    yield Button("Run", id="run")
                    yield Static("|", classes="taskbar-sep")
                    yield Button("Refresh", id="refresh")
                    yield Static("|", classes="taskbar-sep")
                    yield Button("Clear log", id="clear")
                    yield Static("|", classes="taskbar-sep")
                    yield Button("Copy log", id="copy_log")
                    yield Static("|", classes="taskbar-sep")
                    yield Button("Runner: auto", id="runner")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static("Actions", id="actions-title")
                yield OptionList(id="actions")
                yield Static("Select an action and press Enter.", id="details")
                yield Static("Click Run to start | i: interrupt | r: refresh | l: clear log | q: quit", id="hint")
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
        self._render_status()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_stop(self) -> None:
        action = self._selected_action
        if not action:
            return
        state = self._running_actions.get(action.key)
        if not state or not state.proc:
            return
        state.proc.terminate()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        action = self._action_by_key.get(event.option.id or "")
        if not action:
            return
        self._selected_action = action
        self.query_one("#details", Static).update(action.description)
        self._set_active_log(action.key)
        self._render_status()
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
            action = self._selected_action
            if not action:
                return
            log_path = self._log_path_for(action.key)
            if log_path:
                self.set_clipboard(str(log_path))
        elif button_id == "runner":
            self._cycle_runner()

    def _cycle_runner(self) -> None:
        if self._running_actions:
            log = self.query_one("#log", RichLog)
            log.write("[info] Runner mode locked while actions are running.", scroll_end=True)
            return
        order = ["auto", "docker", "wsl"]
        try:
            idx = order.index(self._runner_mode)
        except ValueError:
            idx = 0
        self._runner_mode = order[(idx + 1) % len(order)]
        self._render_status()
        self._sync_toolbar()

    def _busy_resources(self) -> set[str]:
        resources: set[str] = set()
        for state in self._running_actions.values():
            resources.update(state.resources)
        return resources

    def _conflicts_for(self, action: ActionSpec) -> set[str]:
        return set(action.resources_for(self._runner_mode)).intersection(self._busy_resources())

    def _log_path_for(self, action_key: str) -> Path | None:
        state = self._running_actions.get(action_key)
        if state:
            return state.log_path
        last = self._last_runs.get(action_key)
        if last:
            return last.log_path
        return None

    def _set_active_log(self, action_key: str | None) -> None:
        self._active_log_action = action_key
        log = self.query_one("#log", RichLog)
        log.clear()
        if not action_key:
            return
        log_path = self._log_path_for(action_key)
        if not log_path or not log_path.exists():
            return
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in content[-200:]:
            log.write(line, scroll_end=True)

    def _request_run(self, action: ActionSpec) -> None:
        if action.key in self._running_actions:
            return
        if action in self._queued_actions:
            return
        conflicts = self._conflicts_for(action)
        if conflicts:
            self._queued_actions.append(action)
            if self._active_log_action == action.key:
                log = self.query_one("#log", RichLog)
                log.write(
                    f"[queued] waiting for resources: {', '.join(sorted(conflicts))}",
                    scroll_end=True,
                )
            self._render_status()
            self._sync_toolbar()
            return
        self.run_worker(self._execute_action(action), exclusive=False)

    def _try_start_queued(self) -> None:
        if not self._queued_actions:
            return
        pending: list[ActionSpec] = []
        for action in self._queued_actions:
            if self._conflicts_for(action):
                pending.append(action)
                continue
            self.run_worker(self._execute_action(action), exclusive=False)
        self._queued_actions = pending
        self._render_status()
        self._sync_toolbar()

    def _run_selected(self) -> None:
        if not self._selected_action:
            return
        if self._selected_action.key in self._running_actions:
            self.action_stop()
            return
        self._request_run(self._selected_action)

    async def _execute_action(self, action: ActionSpec) -> None:
        if action.key in self._running_actions:
            return
        self._current_action = action
        self._progress_value = 0

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOG_DIR / f"{timestamp}_{action.key}.log"
        state = RunState(
            action=action,
            log_path=log_path,
            start_time=asyncio.get_running_loop().time(),
            resources=frozenset(action.resources_for(self._runner_mode)),
            runner_mode=self._runner_mode,
            proc=None,
        )
        self._running_actions[action.key] = state
        self._sync_toolbar()

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
        command = action.command(state.runner_mode)
        command_line = f"$ {' '.join(command)}"
        if self._active_log_action in (None, action.key):
            self._set_active_log(action.key)
            log.write(command_line, scroll_end=True)

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                cwd=REPO_ROOT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:  # pragma: no cover - UI error path
            if self._active_log_action == action.key:
                log.write(f"[error] Failed to start command: {exc}", scroll_end=True)
            state.exit_code = 1
            self._running_actions.pop(action.key, None)
            self._last_runs[action.key] = state
            if not self._running_actions:
                progress.display = False
                spinner.display = False
                if self._progress_timer:
                    self._progress_timer.pause()
                if self._elapsed_timer:
                    self._elapsed_timer.pause()
            self._render_status()
            self._sync_toolbar()
            self._try_start_queued()
            return

        state.proc = proc

        with log_path.open("w", encoding="utf-8") as handle:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text_line = line.decode(errors="replace").rstrip()
                handle.write(text_line + "\n")
                if self._active_log_action == action.key:
                    log.write(text_line, scroll_end=True)

            await proc.wait()

        state.exit_code = proc.returncode
        self._running_actions.pop(action.key, None)
        self._last_runs[action.key] = state
        if not self._running_actions:
            progress.update(progress=100)
            progress.display = False
            spinner.display = False
            if self._progress_timer:
                self._progress_timer.pause()
            if self._elapsed_timer:
                self._elapsed_timer.pause()
        self._render_status()
        self._sync_toolbar()
        self._try_start_queued()

    def _render_status(self) -> None:
        status_head = self.query_one("#status-head", Static)
        status_lines = self.query_one("#status-lines", Static)
        badge_state = self.query_one("#badge-state", Static)
        badge_exit = self.query_one("#badge-exit", Static)
        badge_elapsed = self.query_one("#badge-elapsed", Static)
        selected = self._selected_action or self._current_action
        action_label = selected.label if selected else "-"
        running_state = self._running_actions.get(selected.key) if selected else None
        if running_state:
            command = " ".join(running_state.action.command(running_state.runner_mode))
        else:
            command = " ".join(selected.command(self._runner_mode)) if selected else "-"
        running_state = self._running_actions.get(selected.key) if selected else None
        queued = selected and any(a.key == selected.key for a in self._queued_actions)
        last_state = self._last_runs.get(selected.key) if selected else None

        log_path = "-"
        elapsed = None
        exit_code = "-"
        state = "Idle"
        if running_state:
            log_path = str(running_state.log_path)
            elapsed = asyncio.get_running_loop().time() - running_state.start_time
            state = "Running"
        elif queued:
            state = "Queued"
            if last_state:
                log_path = str(last_state.log_path)
                exit_code = str(last_state.exit_code) if last_state.exit_code is not None else "-"
        elif last_state:
            log_path = str(last_state.log_path)
            exit_code = str(last_state.exit_code) if last_state.exit_code is not None else "-"

        busy = ", ".join(sorted(self._busy_resources())) or "-"
        status_head.update(action_label)
        status_lines.update(
            "\n".join(
                [
                    f"Command: {command}",
                    f"Log    : {log_path}",
                    f"Runner : {self._runner_mode}",
                    f"Running: {len(self._running_actions)} | Queued: {len(self._queued_actions)} | Busy: {busy}",
                ]
            )
        )
        badge_state.update(state.upper())
        badge_state.set_class(state == "Running", "badge--running")
        badge_exit.update(f"EXIT {exit_code}")
        badge_exit.set_class(exit_code not in ("-", "0"), "badge--error")
        badge_elapsed.update(f"ELAPSED {format_duration(elapsed)}")
        state_suffix = f"{state} ({len(self._running_actions)})" if self._running_actions else state
        self.query_one("#taskbar-state", Static).update(f"* {state_suffix}")

    def _sync_toolbar(self) -> None:
        run_button = self.query_one("#run", Button)
        copy_button = self.query_one("#copy_log", Button)
        runner_button = self.query_one("#runner", Button)
        selected = self._selected_action
        running = bool(selected and selected.key in self._running_actions)
        queued = bool(selected and any(a.key == selected.key for a in self._queued_actions))
        run_button.label = "Interrupt" if running else "Run"
        run_button.variant = "error" if running else "primary"
        if queued and not running:
            run_button.label = "Queued"
            run_button.variant = "default"
        run_button.set_class(bool(selected) and not running and not queued, "run-ready")
        run_button.disabled = selected is None or queued
        copy_button.disabled = self._log_path_for(selected.key) is None if selected else True
        runner_button.label = f"Runner: {self._runner_mode}"
        runner_button.disabled = bool(self._running_actions)

    def _tick_elapsed(self) -> None:
        if not self._running_actions:
            return
        self._render_status()

    def _pulse_progress(self) -> None:
        if not self._running_actions:
            return
        progress = self.query_one("#progress", ProgressBar)
        self._progress_value = (self._progress_value + 3) % 101
        progress.update(progress=self._progress_value)


def run() -> None:
    SiliciumTui().run()
