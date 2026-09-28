from __future__ import annotations

from tools.dev.tui.structured_logs import StructuredProgressTracker, parse_structured_event_line


def test_parse_structured_event_line_accepts_schema_v1() -> None:
    line = (
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.000Z","component":"network-node",'
        '"level":"info","run_id":"run-1","event":"task_received","message":"Task received","payload":{"task_id":"p1"}}'
    )
    event = parse_structured_event_line(line)
    assert event is not None
    assert event.component == "network-node"
    assert event.event == "task_received"
    assert event.payload["task_id"] == "p1"


def test_structured_progress_tracker_handles_mixed_component_success_run() -> None:
    tracker = StructuredProgressTracker()
    lines = [
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.100Z","component":"cli","level":"info","run_id":"run-9","event":"command_started","message":"CLI command started","payload":{"command":"check"}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:01.100Z","component":"workload","level":"info","run_id":"run-9","event":"phase_started","message":"Phase started","payload":{"phase":"render"}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:01.300Z","component":"network-node","level":"info","run_id":"run-9","event":"task_received","message":"Task received by network node","payload":{"task_id":"func_1","total_tasks":2}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:01.400Z","component":"network-node","level":"info","run_id":"run-9","event":"started","message":"Task execution started","payload":{"task_id":"func_1"}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:02.100Z","component":"raytracer","level":"info","run_id":"run-9","event":"execution_completed","message":"Tile execution completed","payload":{"fragment_id":"func_1","success":true}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:02.200Z","component":"network-node","level":"info","run_id":"run-9","event":"finished","message":"Task execution completed","payload":{"task_id":"func_1","success":true}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:03.000Z","component":"cli","level":"info","run_id":"run-9","event":"command_finished","message":"CLI command completed","payload":{"exit_code":0}}',
    ]
    for line in lines:
        tracker.consume_line(line)

    summary = tracker.snapshot()
    assert summary.has_events
    assert summary.state == "done"
    assert summary.progress == 100
    assert summary.source_component == "cli"
    assert summary.source_event == "command_finished"


def test_structured_progress_tracker_surfaces_failure_source() -> None:
    tracker = StructuredProgressTracker()
    lines = [
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.100Z","component":"network-node","level":"info","run_id":"run-2","event":"task_received","message":"Task received by network node","payload":{"task_id":"frag","task_count":1}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.200Z","component":"network-node","level":"info","run_id":"run-2","event":"started","message":"Task execution started","payload":{"task_id":"frag"}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.300Z","component":"network-node","level":"error","run_id":"run-2","event":"failed","message":"Task execution failed","payload":{"task_id":"frag","error":"boom"}}',
        '{"schema_version":1,"timestamp":"2026-02-13T12:00:00.400Z","component":"cli","level":"error","run_id":"run-2","event":"command_finished","message":"CLI command failed","payload":{"exit_code":1}}',
    ]
    for line in lines:
        tracker.consume_line(line)

    summary = tracker.snapshot()
    assert summary.state == "failed"
    assert summary.progress == 100
    assert summary.source_component == "cli"
    assert summary.source_event == "command_finished"
    assert summary.source_message == "CLI command failed"
