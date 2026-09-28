"""Connectors that execute TUI actions: in-process, stdio core, or HTTP endpoint."""
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
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from tools.dev.tui.actions import ActionSpec, REPO_ROOT


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
        env = os.environ.copy()
        env.setdefault("SILICIUM_CLI_STRUCTURED_LOG", str(log_path.with_suffix(".ndjson")))
        env.setdefault("SILICIUM_WORKER_STRUCTURED_LOG", str(log_path.with_suffix(".worker.ndjson")))
        with log_path.open("w", encoding="utf-8") as handle:
            process = subprocess.Popen(
                cmd,
                cwd=REPO_ROOT,
                env=env,
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
                "or build tools/dev/tui/stdio_core.cpp."
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


class HttpConnector(ITuiConnector):
    def __init__(
        self,
        endpoint: str | None = None,
        *,
        poll_interval_sec: float = 0.10,
        request_timeout_sec: float = 5.0,
    ) -> None:
        super().__init__("http")
        configured_endpoint = endpoint or os.environ.get("SILICIUM_TUI_ENDPOINT", "")
        self._endpoint = _normalize_http_endpoint(configured_endpoint)
        self._poll_interval_sec = max(0.01, poll_interval_sec)
        self._request_timeout_sec = max(0.5, request_timeout_sec)

    def run_action(
        self,
        action: ActionSpec,
        runner_mode: str,
        log_path: Path,
        cancel_event: threading.Event,
    ) -> int:
        command = action.command(runner_mode)
        request_payload = {
            "type": "run",
            "action": action.key,
            "runner_mode": runner_mode,
            "cwd": str(REPO_ROOT),
            "command": command,
        }
        start_response = self._request_json("POST", "/command", request_payload)
        run_id = _extract_run_id(start_response)
        if not run_id:
            raise RuntimeError(
                "HTTP connector expected a run identifier in /command response "
                "(accepted: run_id, id, task_id)."
            )

        cursor = 0
        cancel_sent = False
        with log_path.open("w", encoding="utf-8") as handle:
            while True:
                if cancel_event.is_set() and not cancel_sent:
                    self._request_json(
                        "POST",
                        "/command",
                        {"type": "interrupt", "run_id": run_id},
                    )
                    cancel_sent = True

                logs_query = url_parse.urlencode({"run_id": run_id, "cursor": cursor})
                logs_response = self._request_json("GET", f"/logs?{logs_query}")
                cursor = _write_http_logs(handle, logs_response, cursor)

                state_query = url_parse.urlencode({"run_id": run_id})
                state_response = self._request_json("GET", f"/state?{state_query}")
                state = str(state_response.get("status", "")).strip().lower()
                if state in {"completed", "failed", "error", "cancelled", "canceled", "done"}:
                    return _extract_exit_code(state_response, state)

                time.sleep(self._poll_interval_sec)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if payload is None:
            body = None
        else:
            body = json.dumps(payload).encode("utf-8")
        req = url_request.Request(
            f"{self._endpoint}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with url_request.urlopen(req, timeout=self._request_timeout_sec) as response:
                raw = response.read().decode("utf-8").strip()
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"HTTP connector request failed {method} {path}: {exc.code} {details}"
            ) from exc
        except url_error.URLError as exc:
            raise RuntimeError(
                f"HTTP connector request failed {method} {path}: {exc.reason}"
            ) from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"HTTP connector received invalid JSON for {method} {path}"
            ) from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(
                f"HTTP connector expected object response for {method} {path}"
            )
        return parsed


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


def _normalize_http_endpoint(raw: str) -> str:
    endpoint = raw.strip() or "http://127.0.0.1:8765"
    endpoint = endpoint.rstrip("/")
    if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
        endpoint = f"http://{endpoint}"
    return endpoint


def _extract_run_id(payload: dict[str, object]) -> str:
    for key in ("run_id", "id", "task_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return ""


def _extract_exit_code(payload: dict[str, object], state: str) -> int:
    for key in ("exit_code", "code"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    if state == "completed":
        return 0
    return 1


def _write_http_logs(
    handle: "typing.TextIO",
    payload: dict[str, object],
    cursor: int,
) -> int:
    import typing

    lines_obj = payload.get("lines", payload.get("logs", []))
    items: list[tuple[int | None, str]] = []
    if isinstance(lines_obj, list):
        for entry in lines_obj:
            if isinstance(entry, str):
                items.append((None, entry))
                continue
            if not isinstance(entry, dict):
                continue
            text_value = entry.get("line")
            if not isinstance(text_value, str):
                continue
            cursor_value = entry.get("cursor")
            if isinstance(cursor_value, int):
                items.append((cursor_value, text_value))
            else:
                items.append((None, text_value))

    if any(cursor_value is not None for cursor_value, _ in items):
        items.sort(key=lambda item: item[0] if item[0] is not None else 0)

    for cursor_value, text_line in items:
        handle.write(text_line.rstrip("\r\n") + "\n")
        if cursor_value is not None and cursor_value > cursor:
            cursor = cursor_value
        else:
            cursor += 1

    next_cursor = payload.get("next_cursor")
    if isinstance(next_cursor, int) and next_cursor > cursor:
        cursor = next_cursor
    return cursor


def _resolve_stdio_core_command() -> list[str] | None:
    env = os.environ.get("SILICIUM_TUI_STDIO_CORE_CMD", "").strip()
    if env:
        return shlex.split(env, posix=(os.name != "nt"))

    binary_name = "stdio_core.exe" if os.name == "nt" else "stdio_core"
    binary = REPO_ROOT / "tools" / "dev" / "tui" / binary_name
    source = REPO_ROOT / "tools" / "dev" / "tui" / "stdio_core.cpp"
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
        "http": HttpConnector(),
    }
