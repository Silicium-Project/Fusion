"""Parse structured NDJSON log lines into progress updates for the TUI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import json


TERMINAL_EVENTS = {"run_completed", "command_finished"}
RECEIVED_EVENTS = {"task_received"}
START_EVENTS = {"task_started", "started", "execution_started", "phase_started"}
SUCCESS_EVENTS = {"task_finished", "finished", "execution_completed", "phase_completed"}
FAIL_EVENTS = {"task_failed", "failed", "execution_failed", "phase_failed"}


@dataclass(frozen=True)
class StructuredEvent:
    component: str
    event: str
    level: str
    message: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class StructuredProgress:
    has_events: bool
    state: str
    progress: int | None
    source_component: str
    source_event: str
    source_message: str
    queued: int
    running: int
    completed: int
    failed: int
    total: int | None


def parse_structured_event_line(line: str) -> StructuredEvent | None:
    raw = line.strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    schema_version = payload.get("schema_version")
    if schema_version != 1:
        return None

    component = payload.get("component")
    event = payload.get("event")
    level = payload.get("level")
    message = payload.get("message")
    event_payload = payload.get("payload")
    if not all(isinstance(v, str) and v for v in (component, event, level, message)):
        return None
    if not isinstance(event_payload, dict):
        return None

    return StructuredEvent(
        component=component,
        event=event,
        level=level,
        message=message,
        payload=dict(event_payload),
    )


class StructuredProgressTracker:
    def __init__(self) -> None:
        self._has_events = False
        self._state = "idle"
        self._progress: int | None = None
        self._source_component = ""
        self._source_event = ""
        self._source_message = ""
        self._queued = 0
        self._running = 0
        self._completed = 0
        self._failed = 0
        self._total: int | None = None

    def snapshot(self) -> StructuredProgress:
        return StructuredProgress(
            has_events=self._has_events,
            state=self._state,
            progress=self._progress,
            source_component=self._source_component,
            source_event=self._source_event,
            source_message=self._source_message,
            queued=self._queued,
            running=self._running,
            completed=self._completed,
            failed=self._failed,
            total=self._total,
        )

    def consume_line(self, line: str) -> StructuredEvent | None:
        parsed = parse_structured_event_line(line)
        if not parsed:
            return None
        self.consume_event(parsed)
        return parsed

    def consume_event(self, event: StructuredEvent) -> None:
        self._has_events = True
        self._source_component = event.component
        self._source_event = event.event
        self._source_message = event.message
        self._ingest_total_hint(event.payload)

        if event.event in RECEIVED_EVENTS:
            self._queued += 1
        elif event.event in START_EVENTS:
            if self._queued > 0:
                self._queued -= 1
            self._running += 1
        elif event.event in SUCCESS_EVENTS:
            if self._running > 0:
                self._running -= 1
            self._completed += 1
        elif event.event in FAIL_EVENTS:
            if self._running > 0:
                self._running -= 1
            self._failed += 1

        if event.event in TERMINAL_EVENTS:
            self._apply_terminal_state(event)
            self._progress = 100
            return

        self._maybe_expand_total()
        self._state = self._derive_state()
        self._progress = self._derive_progress()

    def _ingest_total_hint(self, payload: Mapping[str, Any]) -> None:
        for key in ("task_count", "total_tasks", "total"):
            value = payload.get(key)
            total = self._parse_non_negative_int(value)
            if total is not None and total > 0:
                self._total = max(total, self._total or 0)
        completed = self._parse_non_negative_int(payload.get("completed"))
        if completed is not None:
            self._completed = max(self._completed, completed)
        failed = self._parse_non_negative_int(payload.get("failed_count"))
        if failed is not None:
            self._failed = max(self._failed, failed)

    def _apply_terminal_state(self, event: StructuredEvent) -> None:
        exit_code = self._parse_int(event.payload.get("exit_code"))
        if event.level == "error" or (exit_code is not None and exit_code != 0):
            self._state = "failed"
            self._failed = max(self._failed, 1)
        else:
            self._state = "done"
            self._completed = max(self._completed, 1)
        self._running = 0
        self._queued = 0
        self._maybe_expand_total()

    def _derive_state(self) -> str:
        if self._failed > 0 and self._running == 0 and self._queued == 0:
            return "failed"
        if self._running > 0:
            return "running"
        if self._queued > 0:
            return "queued"
        if self._completed > 0:
            return "done"
        return "idle"

    def _derive_progress(self) -> int | None:
        total = self._total
        if total and total > 0:
            done = min(total, self._completed + self._failed)
            return min(100, max(0, int((done * 100) / total)))
        if self._state in {"done", "failed"}:
            return 100
        if self._state == "running":
            return 0
        return None

    def _maybe_expand_total(self) -> None:
        observed = self._queued + self._running + self._completed + self._failed
        if observed <= 0:
            return
        if self._total is None:
            self._total = observed
            return
        self._total = max(self._total, observed)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("-"):
                raw = raw[1:]
            if raw.isdigit():
                try:
                    return int(value.strip())
                except ValueError:
                    return None
        return None

    @classmethod
    def _parse_non_negative_int(cls, value: Any) -> int | None:
        parsed = cls._parse_int(value)
        if parsed is None or parsed < 0:
            return None
        return parsed
