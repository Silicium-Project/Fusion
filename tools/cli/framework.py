"""Command framework: command specs and groups, the registry that builds the
argparse tree, and the structured run log (one JSONL file per command run).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.cli.constants import CLI_STRUCTURED_LOG_DIR, CLI_STRUCTURED_LOG_ENV
from tools.cli.context import Context


def _now_rfc3339_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _compact_timestamp_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _generate_run_id() -> str:
    existing = os.environ.get("SILICIUM_RUN_ID", "").strip()
    if existing:
        return existing
    return "cli-" + secrets.token_hex(8)


def _default_cli_structured_log_path(run_id: str) -> Path:
    safe_run_id = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in run_id) or "run"
    return CLI_STRUCTURED_LOG_DIR / f"cli-{_compact_timestamp_utc()}-{safe_run_id}.ndjson"


class StructuredRunLogger:
    def __init__(self, *, component: str, run_id: str, path: Path | None) -> None:
        self.component = component
        self.run_id = run_id
        self.path = path
        self._stream = None
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("a", encoding="utf-8")
        except OSError:
            self._stream = None

    @property
    def enabled(self) -> bool:
        return self._stream is not None

    def emit(self, level: str, event: str, message: str, payload: Mapping[str, Any] | None = None) -> None:
        if not self._stream:
            return
        event_payload = payload if isinstance(payload, Mapping) else {}
        entry = {
            "schema_version": 1,
            "timestamp": _now_rfc3339_utc(),
            "component": self.component,
            "level": level,
            "run_id": self.run_id,
            "event": event,
            "message": message,
            "payload": dict(event_payload),
        }
        self._stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._stream:
            self._stream.close()
            self._stream = None


_ACTIVE_CLI_LOGGER: StructuredRunLogger | None = None


def _emit_cli_event(level: str, event: str, message: str, payload: Mapping[str, Any] | None = None) -> None:
    if _ACTIVE_CLI_LOGGER is None:
        return
    _ACTIVE_CLI_LOGGER.emit(level, event, message, payload)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    configure: Callable[[argparse.ArgumentParser], None]
    handler: Callable[[argparse.Namespace, Context], None]


@dataclass(frozen=True)
class CommandGroup:
    name: str
    help: str
    commands: list[CommandSpec]
    dest: str


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: list[CommandSpec] = []
        self._groups: list[CommandGroup] = []

    def add(self, command: CommandSpec) -> None:
        self._commands.append(command)

    def add_group(self, group: CommandGroup) -> None:
        self._groups.append(group)

    def register(self, parser: argparse.ArgumentParser, ctx: Context) -> None:
        sub = parser.add_subparsers(dest="command", required=True)
        for command in self._commands:
            cmd_parser = sub.add_parser(command.name, help=command.help)
            command.configure(cmd_parser)
            cmd_parser.set_defaults(func=self._wrap(command.handler, ctx))
        for group in self._groups:
            group_parser = sub.add_parser(group.name, help=group.help)
            group_sub = group_parser.add_subparsers(dest=group.dest, required=True)
            for command in group.commands:
                cmd_parser = group_sub.add_parser(command.name, help=command.help)
                command.configure(cmd_parser)
                cmd_parser.set_defaults(func=self._wrap(command.handler, ctx))

    @staticmethod
    def _wrap(handler: Callable[[argparse.Namespace, Context], None], ctx: Context) -> Callable[[argparse.Namespace], None]:
        def _inner(args: argparse.Namespace) -> None:
            global _ACTIVE_CLI_LOGGER

            run_id = _generate_run_id()
            configured_log = os.environ.get(CLI_STRUCTURED_LOG_ENV, "").strip()
            log_path = Path(configured_log).expanduser() if configured_log else _default_cli_structured_log_path(run_id)
            logger = StructuredRunLogger(component="cli", run_id=run_id, path=log_path)
            previous_logger = _ACTIVE_CLI_LOGGER
            _ACTIVE_CLI_LOGGER = logger

            command = getattr(args, "command", "") or ""
            subcommands = [
                value
                for key, value in sorted(vars(args).items())
                if key.endswith("_cmd") and isinstance(value, str) and value
            ]
            command_path = " ".join([command, *subcommands]).strip()
            payload_base = {
                "command": command,
                "command_path": command_path,
                "subcommands": subcommands,
                "cwd": str(Path.cwd()),
            }

            previous_env = {
                "SILICIUM_RUN_ID": os.environ.get("SILICIUM_RUN_ID"),
            }
            os.environ["SILICIUM_RUN_ID"] = run_id

            started_at = time.monotonic()
            _emit_cli_event("info", "command_started", "CLI command started", payload_base)
            try:
                handler(args, ctx)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code in (None, "") else 1)
                payload = {
                    **payload_base,
                    "exit_code": int(code),
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                }
                _emit_cli_event(
                    "info" if int(code) == 0 else "error",
                    "command_finished",
                    "CLI command completed" if int(code) == 0 else "CLI command failed",
                    payload,
                )
                raise
            except Exception as exc:
                payload = {
                    **payload_base,
                    "exit_code": 1,
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                    "error": str(exc),
                }
                _emit_cli_event("error", "command_finished", "CLI command failed", payload)
                raise
            else:
                payload = {
                    **payload_base,
                    "exit_code": 0,
                    "duration_ms": int((time.monotonic() - started_at) * 1000),
                }
                _emit_cli_event("info", "command_finished", "CLI command completed", payload)
            finally:
                for key, value in previous_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                _ACTIVE_CLI_LOGGER = previous_logger
                logger.close()
        return _inner
