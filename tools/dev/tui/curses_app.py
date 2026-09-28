from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
import threading
import time
from collections import deque
from types import ModuleType
import os

from tools.dev.tui.actions import ActionSpec, LOG_DIR, REPO_ROOT, build_actions


@dataclass
class RunState:
    action: ActionSpec
    process: subprocess.Popen[str]
    log_path: Path
    start_time: float
    exit_code: int | None = None


class CursesTui:
    def __init__(self) -> None:
        self.actions = build_actions()
        self.selected = 0
        self.active_log_action = self.actions[0].key if self.actions else None
        self.runner_mode = "auto"
        self.running: dict[str, RunState] = {}
        self.last_runs: dict[str, RunState] = {}
        self.log_tail = deque(maxlen=300)
        self.message = "Ready"
        self._lock = threading.Lock()
        self._quit = False

    def run(self, stdscr: "object", curses_mod: ModuleType) -> None:
        curses_mod.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(120)

        while not self._quit:
            self._poll_processes()
            self._draw(stdscr, curses_mod)
            key = stdscr.getch()
            if key == -1:
                continue
            self._handle_key(key, curses_mod)

        for state in list(self.running.values()):
            if state.process.poll() is None:
                state.process.terminate()

    def _handle_key(self, key: int, curses_mod: ModuleType) -> None:
        if key in (ord("q"), 27):
            self._quit = True
            return
        if key in (curses_mod.KEY_UP, ord("k")):
            self.selected = max(0, self.selected - 1)
            self.active_log_action = self.actions[self.selected].key
            return
        if key in (curses_mod.KEY_DOWN, ord("j")):
            self.selected = min(len(self.actions) - 1, self.selected + 1)
            self.active_log_action = self.actions[self.selected].key
            return
        if key in (10, 13):
            self._run_selected()
            return
        if key == ord("i"):
            self._interrupt_selected()
            return
        if key == ord("r"):
            self.message = "Refreshed"

    def _run_selected(self) -> None:
        action = self.actions[self.selected]
        existing = self.running.get(action.key)
        if existing:
            self._interrupt_selected()
            return
        if self.running:
            self.message = "Busy: interrupt running action first."
            return

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{action.key}.log"
        cmd = action.command(self.runner_mode)
        try:
            process = subprocess.Popen(
                cmd,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self.message = f"Start failed: {exc}"
            return

        state = RunState(
            action=action,
            process=process,
            log_path=log_path,
            start_time=time.monotonic(),
        )
        self.running[action.key] = state
        self.active_log_action = action.key
        self.log_tail.clear()
        self.message = f"Running: {action.label}"
        thread = threading.Thread(target=self._stream_output, args=(state,), daemon=True)
        thread.start()

    def _interrupt_selected(self) -> None:
        action = self.actions[self.selected]
        state = self.running.get(action.key)
        if not state:
            self.message = "No running action selected."
            return
        if state.process.poll() is None:
            state.process.terminate()
            self.message = f"Interrupt requested: {action.label}"
        else:
            self.message = f"Already finished: {action.label}"

    def _stream_output(self, state: RunState) -> None:
        try:
            with state.log_path.open("w", encoding="utf-8") as handle:
                if state.process.stdout:
                    for line in state.process.stdout:
                        text = line.rstrip()
                        handle.write(text + "\n")
                        with self._lock:
                            if self.active_log_action == state.action.key:
                                self.log_tail.append(text)
        except OSError:
            with self._lock:
                self.log_tail.append("[error] failed to write log file")

    def _poll_processes(self) -> None:
        finished: list[str] = []
        for key, state in self.running.items():
            code = state.process.poll()
            if code is None:
                continue
            state.exit_code = code
            self.last_runs[key] = state
            finished.append(key)
            self.message = f"Done: {state.action.label} (exit {code})"
        for key in finished:
            self.running.pop(key, None)

    def _draw(self, stdscr: "object", curses_mod: ModuleType) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        left = max(36, width // 3)

        title = "Silicium curses UI"
        stdscr.addnstr(0, 0, title, width - 1, curses_mod.A_BOLD)
        status = "RUNNING" if self.running else "IDLE"
        stdscr.addnstr(1, 0, f"State: {status} | Runner: {self.runner_mode}", width - 1)
        stdscr.addnstr(2, 0, "Keys: Up/Down select | Enter run | i interrupt | q quit", width - 1)
        stdscr.hline(3, 0, ord("-"), width - 1)

        max_actions = max(1, height - 6)
        for idx, action in enumerate(self.actions[:max_actions]):
            marker = ">" if idx == self.selected else " "
            running = "*" if action.key in self.running else " "
            label = f"{marker}{running} [{action.key}] {action.label}"
            attr = curses_mod.A_REVERSE if idx == self.selected else 0
            stdscr.addnstr(4 + idx, 0, label, left - 1, attr)

        stdscr.vline(3, left, ord("|"), height - 4)
        stdscr.addnstr(4, left + 2, "Log tail", width - left - 3, curses_mod.A_BOLD)

        with self._lock:
            log_lines = list(self.log_tail)
        log_height = max(1, height - 8)
        for idx, line in enumerate(log_lines[-log_height:]):
            stdscr.addnstr(5 + idx, left + 2, line, width - left - 3)

        stdscr.hline(height - 2, 0, ord("-"), width - 1)
        stdscr.addnstr(height - 1, 0, self.message, width - 1)
        stdscr.refresh()


def _load_curses() -> ModuleType:
    try:
        import curses as curses_mod  # type: ignore
    except ModuleNotFoundError as exc:
        if os.name == "nt":
            raise RuntimeError(
                "Python curses backend is missing on Windows. "
                "Install it with: python -m pip install windows-curses "
                "(supported up to Python 3.13)."
            ) from exc
        raise RuntimeError("Python curses backend is unavailable on this system.") from exc
    return curses_mod


def run() -> None:
    curses_mod = _load_curses()
    if not hasattr(curses_mod, "wrapper"):
        raise RuntimeError("curses module unavailable on this platform.")
    app = CursesTui()
    curses_mod.wrapper(lambda stdscr: app.run(stdscr, curses_mod))
