# Structured Logging Schema v1 (NDJSON)

Issue target: #88

Status: Active contract for structured runtime logs.

## Goal

Normalize logs across splitter/executor/worker so parsers and UI can consume one stable event format.

Transport format:
- NDJSON (one JSON object per line)
- UTF-8

## Event Envelope (v1)

Each line MUST be a JSON object with the following required fields:

- `timestamp` (string)
- `component` (string)
- `level` (string)
- `run_id` (string)
- `event` (string)
- `message` (string)
- `payload` (object)

Recommended version field:
- `schema_version` (integer, value `1`)

## Field Semantics and Validation Rules

### Required fields

- `timestamp`
  - RFC3339 UTC timestamp (example: `2026-02-13T12:34:56.789Z`)
  - Producer clock time when event is emitted.
- `component`
  - Producer identifier. Allowed values for v1:
    - `splitter`
    - `executor`
    - `worker`
    - `cli` (when orchestration emits structured events)
- `level`
  - One of: `debug`, `info`, `warn`, `error`.
- `run_id`
  - Correlation ID for one logical run spanning CLI → worker → executor when applicable.
  - Must be non-empty and stable for the run lifetime.
- `event`
  - Machine-oriented event key in `snake_case` (example: `task_started`, `fragment_executed`).
- `message`
  - Human-readable short summary of the event.
- `payload`
  - JSON object containing event-specific structured data.
  - Never a string/array/null.

### Optional fields

- `schema_version` (integer)
  - Must be `1` for this contract.
- `trace_id` / `span_id` (string) when tracing is enabled.
- `module` (string) for sub-component granularity.

### Encoding constraints

- One event per line (no multiline JSON objects).
- Newlines in textual data must be escaped inside JSON strings.
- Sensitive values (secrets/tokens) must not be logged in cleartext.

## Compatibility and Versioning

`schema_version=1` compatibility rules:

- **Patch-compatible changes**
  - add new optional payload keys
  - add new event names
  - add new optional top-level fields
- **Breaking changes (require v2)**
  - remove or rename required fields
  - change required field types
  - change required semantics (`run_id` correlation meaning, timestamp format)

Consumer rule:
- Consumers must ignore unknown fields and unknown payload keys.

## Examples (NDJSON lines)

### Splitter

```json
{"schema_version":1,"timestamp":"2026-02-13T12:00:00.100Z","component":"splitter","level":"info","run_id":"run-9e95","event":"partition_completed","message":"Partitioning completed","payload":{"binary":"demo.bin","fragments":12,"summary_path":"splitter/run_output/demo/summary.json"}}
```

### Executor

```json
{"schema_version":1,"timestamp":"2026-02-13T12:00:01.450Z","component":"executor","level":"info","run_id":"run-9e95","event":"fragment_executed","message":"Fragment executed in emulator mode","payload":{"fragment_id":"func_6_main","mode":"emu","success":true,"instructions":1842,"memory_accesses":223}}
```

### Worker

```json
{"schema_version":1,"timestamp":"2026-02-13T12:00:02.020Z","component":"worker","level":"warn","run_id":"run-9e95","event":"routing_decision","message":"Native backend unavailable, fallback to emulator","payload":{"required_backend":"native","selected_backend":"emu","reason":"capability_missing"}}
```

## Follow-up issues bound to this contract

- #89 (splitter structured logs)
- #90 (executor structured logs)
- #91 (worker/CLI structured logs)
