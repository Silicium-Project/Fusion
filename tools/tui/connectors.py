from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import threading
import time

from tools.tui.actions import ActionSpec, REPO_ROOT


class ITuiConnector(ABC):
    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def run_action(
        self,
        action: ActionSpec,
        runner_mode: str,
        log_path: Path,
        cancel_event: threading.Event,
    ) -> int:
        pass


class InProcessConnector(ITuiConnector):
    def __init__(self) -> None:
        super().__init__("inprocess")

    def run_action(
        self,
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


def build_connector_registry() -> dict[str, ITuiConnector]:
    return {
        "inprocess": InProcessConnector(),
    }
