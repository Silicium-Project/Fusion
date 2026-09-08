# MCP control-plane contract

Network's MCP server is the authenticated control and observation surface used
by Fusion's private experiment API. It reads node exports and publishes
structured task, result, telemetry, and health resources. It is not a wrapper
around the removed C++ fragment runtime.

## Active implementation

- Server: `tools/mcp_server.py`.
- Default local export: `.silicium/mcp/export/`.
- Auth: bearer token supplied by the caller or the local token file.
- Host deployment: `Fusion/deploy/systemd/silicium-experiment-api.service`.
- Read/write scope is controlled by tool/resource allow and deny lists.

## Resources

- `resources://silicium/status/current`
- `resources://silicium/reports/recent`
- `resources://silicium/results/by-task/{task_id}`
- `resources://silicium/logs/by-task/{task_id}`
- `resources://silicium/tasks/by-id/{task_id}`
- `resources://silicium/requests/by-id/{request_id}`
- `resources://silicium/nodes/heartbeat/{node_id}`
- `resources://silicium/nodes/metrics/{node_id}`

## Tools

- `tools.silicium.run_action`
- `tools.silicium.interrupt_action`
- `tools.silicium.select_runner_mode`
- `tools.silicium.get_health`
- `tools.silicium.submit_task`
- `tools.silicium.get_task`
- `tools.silicium.submit_request`
- `tools.silicium.get_request`

## Event envelope

```json
{
  "schema_version": 1,
  "timestamp": "2026-09-08T12:00:00.000Z",
  "component": "network-node",
  "level": "info",
  "run_id": "run-9e95",
  "event": "task_completed",
  "message": "Task completed",
  "payload": {"task_id": "task-1", "status": "succeeded"}
}
```

Error envelope:

```json
{
  "schema_version": "1.0",
  "error_code": "connector_unavailable",
  "message": "human readable",
  "retryable": true,
  "details": {}
}
```

## Design Pattern Constraints

- Strategy: `IConnectorAdapter` with implementations per frontend protocol (`MCP`, `HTTP`, `InProcess`).
- Factory: one selector for adapter instantiation from config/runtime flags.
- Observer: event stream from worker reporter into bridge subscribers.
- Anti-corruption layer: MCP DTOs isolated from internal C++ structs.

## Security and Stability

- No direct shell command pass-through from MCP tools.
- Allowlist action names; reject unknown action ids.
- Redact sensitive fields from logs/resources before publication.
- Enforce per-tool timeout and max payload size.
- Maintain bounded in-memory history; spill full logs to files.

## Rollout Plan

1. Add bridge interfaces and schema types only (no runtime wiring change).
2. Implement read-only MCP resources backed by existing reports.
3. Add guarded control tools (`run_action`, `interrupt_action`) behind feature flag.
4. Add telemetry for bridge latency/errors in `TaskTelemetry`.
5. Enable by default once CI validates linux + windows flows.

## Current Runtime Hook (step 3)

- Worker CLI flag: `--mcp-readonly`
- Worker CLI flag: `--mcp-enable-tools` (guarded control tools)
- Optional export: `--mcp-export-dir <path>`
- Environment equivalents:
- `SILICIUM_MCP_READONLY=1`
- `SILICIUM_MCP_ENABLE_TOOLS=1`
- `SILICIUM_MCP_EXPORT_DIR=<path>`
- Exported snapshots:
- `status.current.json`
- `reports.recent.json`
- `result.<task_id>.json`
- `logs.<task_id>.json`

### Guarded `run_action` allowlist

When `--mcp-enable-tools` (or `SILICIUM_MCP_ENABLE_TOOLS=1`) is enabled:

- `action=get_health_snapshot` -> returns `resources://silicium/status/current`
- `action=read_recent_reports` -> returns `resources://silicium/reports/recent`
- `action=read_task_result` + `task_id` -> returns `resources://silicium/results/by-task/{task_id}`
- `action=read_submitted_task` + `task_id` -> returns `resources://silicium/tasks/by-id/{task_id}`
- `action=read_submitted_request` + `request_id` -> returns `resources://silicium/requests/by-id/{request_id}`

Any other action is rejected with `error_code=action_not_allowed`.

### Task ingress

With `--mcp-enable-tools`, clients can submit tasks to the local network ingress without launching devnet flow scripts:

- `POST /tasks` with `{"task_id":"optional-id","task":{...}}`
- `POST /tools` with `{"name":"tools.silicium.submit_task","args":{"task":{...}}}`

Accepted tasks are role-aware. Envelopes include `required_roles`, `priority`, optional `p2p_ref`, and `response_mode`. Supported roles are `compute`, `verify`, `storage`, `audit`, and `resource`.

Large payloads should not be embedded in the task body. Put them in the P2P layer and pass a content reference:

```json
{
  "task": {"kind": "storage", "manifest": "render-42"},
  "required_roles": ["storage"],
  "priority": "high",
  "p2p_ref": {"protocol": "ipfs", "cid": "bafy...", "hash": "sha256:..."}
}
```

Accepted tasks are stored as `.json` envelopes in the export directory under `tasks/`, appended to `tasks.queue.ndjson`, and mirrored into the first role queue such as `tasks.storage.queue.ndjson`. Submitted task envelopes are readable through:

- `GET /tasks/<task_id>`
- `resources://silicium/tasks/by-id/{task_id}`
- `tools.silicium.get_task`

### Fast request inbox

Post-job requests are separate from normal task submission so nodes can react quickly to audits, challenges, replication, pin/unpin, retrieval, health checks, and resource requests:

- `POST /requests` with `{"kind":"audit","priority":"urgent","target_roles":["audit","verify"],"p2p_ref":{...}}`
- `POST /tools` with `{"name":"tools.silicium.submit_request","args":{"kind":"resource","p2p_ref":{...}}}`

Accepted requests are stored under `requests/`, appended to `requests.queue.ndjson`, mirrored into role queues such as `requests.audit.queue.ndjson`, and high/urgent requests are also appended to `requests.urgent.ndjson`.

Request envelopes are readable through:

- `GET /requests/<request_id>`
- `resources://silicium/requests/by-id/{request_id}`
- `tools.silicium.get_request`

### Node daemon

`silicium node start` runs the role-aware local daemon that consumes ingress envelopes as a service instead of requiring one-off scripts. The launcher now starts the Rust `p2p_node` binary directly, and `SILICIUM_P2P_NODE_BIN` can override the executable.

```bash
silicium node start --roles compute,verify,storage,audit,resource
```

Scheduling order is intentionally biased toward fast reaction:

1. `requests.urgent.ndjson`
2. role-specific request queues such as `requests.audit.queue.ndjson`
3. general `requests.queue.ndjson`
4. role-specific task queues such as `tasks.storage.queue.ndjson`
5. general `tasks.queue.ndjson`

The daemon keeps cursor/idempotency state under `node-state/<node-id>/`, fetches referenced payloads through the P2P gateway or local P2P cache, writes `result.<id>.json` and `logs.<id>.json`, and updates the original task/request envelope status to `completed` or `failed`.

When Solana execution is enabled, the same daemon also publishes the relevant state transitions to the on-chain program. This is still one service entrypoint:

```bash
silicium node start \
  --roles compute,verify,storage,audit,resource \
  --solana-enable \
  --solana-program-id HyXT83SzHsEPxNZ5zQPvkLwQ7JwFHh2veAE5PuGUgoiQ \
  --solana-wallet ~/.config/solana/id.json
```

Task envelopes can carry an `on_chain` block. For compute work, the node performs local/P2P work, then calls `claimFragment` and `submitFragmentResult` with the produced result hash and proof reference:

```json
{
  "task": {"kind": "compute"},
  "required_roles": ["compute"],
  "p2p_ref": {"protocol": "ipfs", "cid": "bafy..."},
  "on_chain": {
    "job": "job-pubkey",
    "fragment_index": 0,
    "worker_token": "worker-token-account"
  }
}
```

For storage work, the node calls `declareJobStorage` when the job and hashes are available. For audit/challenge/verify requests, the urgent request inbox can carry an `on_chain` block with `job`, `fragment` or `fragment_index`, `escrow`, and `worker_token`; the node responds with `voteFragment`.

Large data still moves off-chain through `p2p_ref`; only compact hashes, proof references, votes, and storage declarations are committed on-chain.

The node runtime now dispatches work by role:

- `compute`: runs the C++ worker binary when the task has `summary`/`summary_path`, otherwise produces a deterministic local result hash.
- `storage`: pins/replicates the payload into the local content-addressed P2P cache and emits a storage manifest.
- `verify`: checks the payload hash against `expected_hash` and exposes the boolean as the vote choice.
- `audit`, `challenge`, `retrieve`, `pin`, `unpin`, `replicate`, `health`, and `resource` requests are handled through the fast request inbox before normal task queues.

Operational files written by the daemon:

- `node.<node-id>.heartbeat.json`: current roles, capacity, worker mode, Solana status.
- `node.<node-id>.metrics.json`: handled, failed, retried, and dead-letter counters.
- `retries.ndjson`: transient failures requeued with an incremented attempt.
- `dead_letters.ndjson`: permanently failed envelopes after `--max-retries`.
- `node.events.ndjson`: lifecycle and processing events.

The CLI can submit and read work directly from the same ingress:

```bash
python silicium node submit-task \
  --task-id demo:storage \
  --roles storage \
  --task '{"kind":"storage","path":"object.bin"}' \
  --p2p-ref '{"protocol":"file","content_id":"/tmp/object.bin"}'

python silicium node get-task demo:storage
python silicium node get-result demo:storage

python silicium node submit-request \
  --request-id audit:demo \
  --kind audit \
  --roles audit,verify \
  --priority urgent \
  --request '{"expected_hash":"sha256:..."}' \
  --p2p-ref '{"protocol":"ipfs","cid":"bafy..."}'

python silicium node create-job \
  --mint <mint-pubkey> \
  --client-token <client-token-account> \
  --escrow-keypair-path ~/.config/solana/escrow.json \
  --job-id 42 \
  --expected-fragments 1 \
  --reward-per-fragment 1000 \
  --deadline-unix 1893456000 \
  --task '{"kind":"compute","summary":"demo/worker/summary.json","partition_id":"func_1_main"}' \
  --worker-token <worker-token-account>

python silicium node fetch-job --job <job-pubkey>
python silicium node fetch-fragment --job <job-pubkey> --fragment-index 0
python silicium node bootstrap-worker
python silicium node get-heartbeat --node-id node-1234
python silicium node get-metrics --node-id node-1234
```

A systemd template is available at `infra/systemd/silicium-node.service` for a stable auto-restarting node service.

### Guarded control tools (current behavior)

With `--mcp-enable-tools`:

- `tools.silicium.interrupt_action` -> registers an interrupt request consumed by the worker loop before the next task starts.
- `tools.silicium.select_runner_mode` with `{"mode":"auto|emu|native|dynamo"}` -> registers a mode switch consumed before the next task.

Invalid payloads return `error_code=bad_request`.

## Standalone MCP HTTP Server (v1)

The repo includes a minimal local-only HTTP server that serves the exported MCP resources for external clients.

- Script: `tools/mcp_server.py`
- Default bind: `127.0.0.1` (local-only)
- Export directory: passed via `--export-dir` or `SILICIUM_MCP_EXPORT_DIR`
- Optional snapshots: `--snapshot-dir <path>` (or `SILICIUM_MCP_SNAPSHOT_DIR`).
- Retention controls: `--snapshot-max-files` and `--snapshot-max-bytes`.
- Optional auth: `SILICIUM_MCP_TOKEN` (Bearer token), disabled with `--no-auth`
- Access control (optional): `--tool-allowlist`, `--tool-denylist`, `--resource-allowlist`, `--resource-denylist`

Run worker + export:

```bash
./worker --summary summary.json --queue queue.txt --mcp-readonly --mcp-export-dir /tmp/silicium-mcp
```

Run server (read-only resources):

```bash
python silicium mcp serve --export-dir /tmp/silicium-mcp
```

Enable guarded tools (writes `control.request.json` in export dir):

```bash
python silicium mcp serve --export-dir /tmp/silicium-mcp --enable-tools
```

Disable auth even when token env/file exists:

```bash
python silicium mcp serve --export-dir /tmp/silicium-mcp --no-auth
```

Endpoints:

- `GET /healthz`
- `GET /metrics` (Prometheus text format)
- `GET /resources/list`
- `GET /resources?uri=resources://...`
- `GET /tools/list`
- `GET /snapshots/list` (when snapshots are enabled)
- `GET /snapshots/export` (offline bundle export)
- `GET /.well-known/oauth-authorization-server`
- `GET /.well-known/oauth-authorization-server/mcp`
- `GET /mcp/.well-known/oauth-authorization-server`
- `POST /tools` with `{"name":"tools.silicium.get_health","args":{}}`
- `POST /tasks` with `{"task":{"partition_id":"func_1_main","inputs":{"rax":"0x1"}}}`
- `POST /requests` with `{"kind":"audit","priority":"urgent","p2p_ref":{"protocol":"ipfs","cid":"bafy..."}}`
- `POST /snapshots/import` with export bundle payload

OAuth discovery endpoints return `200` with `oauth_not_supported` metadata so MCP clients probing OAuth routes do not receive `404`.
Allow/deny lists accept comma-separated exact names or prefix rules ending with `*` (for example `resources://silicium/results/by-task/*`).

Logging:

- `--log-format text|json` controls lifecycle + request logs emitted on stdout.
- `json` mode emits structured events (`listen`, `http_request`, `tool_call`) with latency/status fields.

Prometheus metrics (non-exhaustive):

- `mcp_http_requests_total{method,path,status}`
- `mcp_http_request_duration_seconds_{sum,count}{method,path}`
- `mcp_jsonrpc_calls_total{method,is_error}`
- `mcp_tool_calls_total{tool}`
- `mcp_tool_failures_total{tool}`
- `mcp_tool_call_duration_seconds_{sum,count}{tool}`

### Standardized local configuration

To keep configuration minimal, `python silicium mcp serve` and `python silicium mcp print-config` resolve settings with:

- CLI flags (lowest priority, only for overrides)
- Environment variables (`SILICIUM_MCP_*`)
- Local file: `.silicium/config.json` (or `SILICIUM_CONFIG=/path/to/config.json`)
- Defaults

Default local paths (repo-relative):

- export dir: `.silicium/mcp/export/`
- token file: `.silicium/mcp/token`
- access policy env vars: `SILICIUM_MCP_TOOL_ALLOWLIST`, `SILICIUM_MCP_TOOL_DENYLIST`, `SILICIUM_MCP_RESOURCE_ALLOWLIST`, `SILICIUM_MCP_RESOURCE_DENYLIST`

## References

- `worker/include/worker/backend/BackendConnector.hpp`
- `worker/include/worker/backend/BackendConnectorFactory.hpp`
- `worker/include/worker/task/TaskReport.hpp`
- `worker/include/worker/task/TaskTelemetry.hpp`
- `worker/include/worker/task/TaskSerializer.hpp`
- `tools/tui/app.py`
- `docs/network-schema.md`
