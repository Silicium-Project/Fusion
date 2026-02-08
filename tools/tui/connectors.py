from __future__ import annotations

from abc import ABC, abstractmethod
import base64
import json
import os
from pathlib import Path
import queue
import shlex
import shutil
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


class StdIoConnector(ITuiConnector):
    def __init__(self, core_command: list[str] | None = None) -> None:
        super().__init__("stdio")
        self._core_command = core_command
        self._resolved_default = core_command is not None

    def run_action(
        self,
        action: ActionSpec,
        runner_mode: str,
        log_path: Path,
        cancel_event: threading.Event,
    ) -> int:
        if not self._resolved_default:
            self._core_command = _resolve_stdio_core_command()
            self._resolved_default = True
        if not self._core_command:
            raise RuntimeError(
                "StdIO core is unavailable. Set SILICIUM_TUI_STDIO_CORE_CMD "
                "or build tools/tui/stdio_core.cpp."
            )

        command = action.command(runner_mode)
        command_line = (
            subprocess.list2cmdline(command)
            if os.name == "nt"
            else shlex.join(command)
        )
        payload = {
            "type": "run",
            "action": action.key,
            "runner_mode": runner_mode,
            "cwd_b64": _b64_encode(str(REPO_ROOT)),
            "command_b64": _b64_encode(command_line),
        }

        with log_path.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                self._core_command,
                cwd=REPO_ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert process.stdin is not None
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()
            process.stdin.close()

            line_queue: queue.Queue[str | None] = queue.Queue()
            reader = threading.Thread(
                target=self._reader_loop,
                args=(process, line_queue),
                daemon=True,
            )
            reader.start()

            reported_exit: int | None = None
            try:
                while True:
                    if cancel_event.is_set() and process.poll() is None:
                        process.terminate()

                    try:
                        line = line_queue.get(timeout=0.05)
                    except queue.Empty:
                        if process.poll() is not None and not reader.is_alive():
                            break
                        continue

                    if line is None:
                        break

                    event = _parse_event_line(line)
                    if event and event.get("type") == "log":
                        text_line = str(event.get("line", ""))
                        handle.write(text_line + "\n")
                        continue
                    if event and event.get("type") == "state":
                        exit_code = event.get("exit_code")
                        if isinstance(exit_code, int):
                            reported_exit = exit_code
                        continue
                    handle.write(line.rstrip("\r\n") + "\n")
            finally:
                if process.poll() is None:
                    process.kill()

            return_code = process.wait()
            return int(reported_exit if reported_exit is not None else return_code)

    @staticmethod
    def _reader_loop(
        process: subprocess.Popen[str],
        line_queue: queue.Queue[str | None],
    ) -> None:
        try:
            if process.stdout:
                for line in process.stdout:
                    line_queue.put(line)
        finally:
            line_queue.put(None)


def _parse_event_line(line: str) -> dict[str, object] | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _b64_encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _resolve_stdio_core_command() -> list[str] | None:
    env = os.environ.get("SILICIUM_TUI_STDIO_CORE_CMD", "").strip()
    if env:
        return shlex.split(env, posix=(os.name != "nt"))

    binary_name = "stdio_core.exe" if os.name == "nt" else "stdio_core"
    binary = REPO_ROOT / "tools" / "tui" / binary_name
    source = REPO_ROOT / "tools" / "tui" / "stdio_core.cpp"
    if binary.exists():
        return [str(binary)]
    if not source.exists():
        return None
    if _try_build_stdio_core(source, binary):
        return [str(binary)]
    return None


def _try_build_stdio_core(source: Path, output: Path) -> bool:
    compiler = (
        os.environ.get("SILICIUM_TUI_STDIO_CXX", "").strip()
        or shutil.which("g++")
        or shutil.which("clang++")
        or shutil.which("c++")
    )
    if not compiler:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [compiler, "-std=c++17", "-O2", str(source), "-o", str(output)]
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    return output.exists()


def build_connector_registry() -> dict[str, ITuiConnector]:
    return {
        "inprocess": InProcessConnector(),
        "stdio": StdIoConnector(),
    }
