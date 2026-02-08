from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from tools.tui.actions import ActionSpec
from tools.tui.headless_app import HeadlessScheduler, run_script


REPO_ROOT = Path(__file__).resolve().parents[1]


def _action(
    key: str,
    *,
    resources: frozenset[str] = frozenset(),
) -> ActionSpec:
    return ActionSpec(
        key=key,
        label=key,
        args=["status"],
        description=f"action {key}",
        resources=resources,
    )


def test_headless_scheduler_run_and_state_transitions(tmp_path: Path) -> None:
    action = _action("a")

    def runner(_action, _runner_mode, log_path, _cancel_event):
        log_path.write_text("ok\n", encoding="utf-8")
        return 0

    scheduler = HeadlessScheduler(
        actions=[action],
        log_dir=tmp_path,
        command_runner=runner,
    )
    scheduler.schedule("a")
    assert scheduler.wait_for_all(timeout_sec=2.0)
    record = scheduler.get("a")
    assert record is not None
    assert record.status == "completed"
    assert record.exit_code == 0
    assert "running" in record.history
    assert "completed" in record.history


def test_headless_scheduler_queues_conflicting_resources(tmp_path: Path) -> None:
    action_a = _action("a", resources=frozenset({"docker"}))
    action_b = _action("b", resources=frozenset({"docker"}))
    release_a = threading.Event()

    def runner(action, _runner_mode, log_path, _cancel_event):
        log_path.write_text(f"{action.key}\n", encoding="utf-8")
        if action.key == "a":
            release_a.wait(timeout=2.0)
        return 0

    scheduler = HeadlessScheduler(
        actions=[action_a, action_b],
        log_dir=tmp_path,
        command_runner=runner,
    )

    scheduler.schedule("a")
    scheduler.schedule("b")
    record_b = scheduler.get("b")
    assert record_b is not None
    assert record_b.status == "queued"

    release_a.set()
    assert scheduler.wait_for_all(timeout_sec=3.0)
    assert scheduler.get("a").status == "completed"  # type: ignore[union-attr]
    assert scheduler.get("b").status == "completed"  # type: ignore[union-attr]
    assert "queued" in scheduler.get("b").history  # type: ignore[union-attr]
    assert "running" in scheduler.get("b").history  # type: ignore[union-attr]


def test_headless_scheduler_interrupt(tmp_path: Path) -> None:
    action = _action("long")

    def runner(_action, _runner_mode, _log_path, cancel_event):
        for _ in range(200):
            if cancel_event.is_set():
                return 130
            time.sleep(0.005)
        return 0

    scheduler = HeadlessScheduler(
        actions=[action],
        log_dir=tmp_path,
        command_runner=runner,
    )
    scheduler.schedule("long")
    time.sleep(0.03)
    assert scheduler.interrupt("long")
    assert scheduler.wait_for_all(timeout_sec=3.0)
    record = scheduler.get("long")
    assert record is not None
    assert record.status == "interrupted"
    assert record.exit_code == 130


def test_headless_script_executes_sequence(tmp_path: Path) -> None:
    action_a = _action("a", resources=frozenset({"docker"}))
    action_b = _action("b", resources=frozenset({"docker"}))
    release_a = threading.Event()
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            {
                "runner_mode": "auto",
                "steps": [
                    {"run": "a"},
                    {"run": "b"},
                    {"sleep_ms": 20},
                    {"wait_all": True, "timeout_sec": 2},
                ],
            }
        ),
        encoding="utf-8",
    )

    def runner(action, _runner_mode, log_path, _cancel_event):
        log_path.write_text(action.key + "\n", encoding="utf-8")
        if action.key == "a":
            release_a.set()
            time.sleep(0.05)
        return 0

    snapshot = run_script(
        script,
        actions=[action_a, action_b],
        timeout_sec=3.0,
        log_dir=tmp_path,
        command_runner=runner,
    )
    records = snapshot["records"]
    assert records["a"]["status"] == "completed"
    assert records["b"]["status"] == "completed"


def test_tui_headless_smoke_command() -> None:
    result = subprocess.run(
        [sys.executable, "silicium", "tui", "--smoke", "--tui-frontend", "headless"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0
    assert "Frontend headless: OK" in result.stdout
