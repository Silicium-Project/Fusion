from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from tools.tui.actions import ActionSpec, LOG_DIR, REPO_ROOT, build_actions

RunStatus = str
CommandRunner = Callable[[ActionSpec, str, Path, threading.Event], int]


@dataclass
class RunRecord:
    action_key: str
    status: RunStatus
    runner_mode: str
    resources: frozenset[str]
    log_path: Path
    exit_code: int | None = None
    started_at: float | None = None
    ended_at: float | None = None
    history: list[RunStatus] = field(default_factory=list)

    def transition(self, status: RunStatus) -> None:
        if self.status == status:
            return
        self.status = status
        self.history.append(status)


@dataclass
class _RunningTask:
    record: RunRecord
    action: ActionSpec
    cancel_event: threading.Event
    thread: threading.Thread


def _default_command_runner(
    action: ActionSpec,
    runner_mode: str,
    log_path: Path,
    cancel_event: threading.Event,
) -> int:
    cmd = action.command(runner_mode)
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        try:
            while True:
                if cancel_event.is_set() and process.poll() is None:
                    process.terminate()
                line = process.stdout.readline() if process.stdout else ""
                if line:
                    handle.write(line)
                elif process.poll() is not None:
                    break
                else:
                    time.sleep(0.01)
        finally:
            if process.poll() is None:
                process.kill()
        return process.wait()


class HeadlessScheduler:
    def __init__(
        self,
        *,
        actions: Iterable[ActionSpec] | None = None,
        runner_mode: str = "auto",
        log_dir: Path = LOG_DIR,
        command_runner: CommandRunner | None = None,
    ) -> None:
        self._actions = {action.key: action for action in (actions or build_actions())}
        self._runner_mode = runner_mode
        self._log_dir = log_dir
        self._command_runner = command_runner or _default_command_runner

        self._records: dict[str, RunRecord] = {}
        self._running: dict[str, _RunningTask] = {}
        self._queue: deque[ActionSpec] = deque()
        self._lock = threading.Lock()

    def schedule(self, action_key: str) -> RunRecord:
        action = self._actions.get(action_key)
        if not action:
            raise KeyError(f"Unknown action key '{action_key}'")
        with self._lock:
            if action_key in self._running:
                return self._records[action_key]
            if any(queued.key == action_key for queued in self._queue):
                return self._records[action_key]

            resources = frozenset(action.resources_for(self._runner_mode))
            record = self._records.get(action_key)
            if not record:
                record = self._new_record(action, resources)
                self._records[action_key] = record

            if self._has_conflict(resources):
                record.transition("queued")
                self._queue.append(action)
                return record
            self._start_locked(action, record, resources)
            return record

    def interrupt(self, action_key: str) -> bool:
        with self._lock:
            running = self._running.get(action_key)
            if not running:
                return False
            running.cancel_event.set()
            running.record.transition("interrupting")
            return True

    def get(self, action_key: str) -> RunRecord | None:
        with self._lock:
            return self._records.get(action_key)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            running = sorted(self._running.keys())
            queued = [action.key for action in self._queue]
            return {
                "running": running,
                "queued": queued,
                "records": {
                    key: {
                        "status": record.status,
                        "exit_code": record.exit_code,
                        "runner_mode": record.runner_mode,
                        "resources": sorted(record.resources),
                        "log_path": str(record.log_path),
                        "history": list(record.history),
                    }
                    for key, record in self._records.items()
                },
            }

    def wait_for_all(self, timeout_sec: float = 120.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            with self._lock:
                done = not self._running and not self._queue
                threads = [item.thread for item in self._running.values()]
            if done:
                return True
            for thread in threads:
                thread.join(timeout=0.02)
            time.sleep(0.01)
        return False

    def _new_record(self, action: ActionSpec, resources: frozenset[str]) -> RunRecord:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_path = self._log_dir / f"{stamp}_{action.key}.log"
        return RunRecord(
            action_key=action.key,
            status="pending",
            runner_mode=self._runner_mode,
            resources=resources,
            log_path=log_path,
            history=["pending"],
        )

    def _has_conflict(self, resources: frozenset[str]) -> bool:
        if not resources:
            return False
        for item in self._running.values():
            if item.record.resources.intersection(resources):
                return True
        return False

    def _start_locked(
        self,
        action: ActionSpec,
        record: RunRecord,
        resources: frozenset[str],
    ) -> None:
        cancel_event = threading.Event()
        record.resources = resources
        record.runner_mode = self._runner_mode
        record.started_at = time.monotonic()
        record.transition("running")
        thread = threading.Thread(
            target=self._run_action,
            args=(action, record, cancel_event),
            daemon=True,
        )
        self._running[action.key] = _RunningTask(
            record=record,
            action=action,
            cancel_event=cancel_event,
            thread=thread,
        )
        thread.start()

    def _run_action(
        self,
        action: ActionSpec,
        record: RunRecord,
        cancel_event: threading.Event,
    ) -> None:
        exit_code = 1
        try:
            exit_code = self._command_runner(
                action,
                self._runner_mode,
                record.log_path,
                cancel_event,
            )
        except Exception:
            exit_code = 1
        finally:
            with self._lock:
                record.exit_code = int(exit_code)
                record.ended_at = time.monotonic()
                if cancel_event.is_set():
                    record.transition("interrupted")
                elif exit_code == 0:
                    record.transition("completed")
                else:
                    record.transition("failed")
                self._running.pop(action.key, None)
                self._drain_queue_locked()

    def _drain_queue_locked(self) -> None:
        if not self._queue:
            return
        pending: deque[ActionSpec] = deque()
        while self._queue:
            action = self._queue.popleft()
            record = self._records[action.key]
            resources = frozenset(action.resources_for(self._runner_mode))
            if self._has_conflict(resources):
                pending.append(action)
                continue
            self._start_locked(action, record, resources)
        self._queue = pending


def run_script(
    script_path: Path,
    *,
    actions: Iterable[ActionSpec] | None = None,
    runner_mode: str = "auto",
    timeout_sec: float = 120.0,
    log_dir: Path = LOG_DIR,
    command_runner: CommandRunner | None = None,
) -> dict[str, object]:
    payload = json.loads(script_path.read_text(encoding="utf-8-sig"))
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Headless script requires a 'steps' array")
    script_runner_mode = payload.get("runner_mode", runner_mode)
    scheduler = HeadlessScheduler(
        actions=actions,
        runner_mode=script_runner_mode,
        log_dir=log_dir,
        command_runner=command_runner,
    )
    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"step {idx} must be an object")
        if "run" in step:
            scheduler.schedule(str(step["run"]))
        elif "interrupt" in step:
            scheduler.interrupt(str(step["interrupt"]))
        elif "sleep_ms" in step:
            sleep_ms = int(step["sleep_ms"])
            if sleep_ms < 0:
                raise ValueError(f"step {idx} sleep_ms must be >= 0")
            time.sleep(sleep_ms / 1000.0)
        elif "wait_all" in step:
            step_timeout = float(step.get("timeout_sec", timeout_sec))
            ok = scheduler.wait_for_all(step_timeout)
            if not ok:
                raise TimeoutError("headless script timed out while waiting for actions")
        else:
            raise ValueError(f"step {idx} has unsupported operation")
    ok = scheduler.wait_for_all(timeout_sec)
    if not ok:
        raise TimeoutError("headless run timed out")
    return scheduler.snapshot()
