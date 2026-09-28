# Structured logging schema v1

Active Network components emit UTF-8 NDJSON: one JSON object per line. The
schema is shared by the CLI, network node, workload runners, MCP server, and
P2P/RPC helpers.

Required fields:

- `timestamp`: RFC3339 UTC string;
- `component`: `cli`, `network-node`, `p2p`, `raytracer`, `mcp`, or another
  registered active component;
- `level`: `debug`, `info`, `warn`, or `error`;
- `run_id`: non-empty correlation identifier;
- `event`: `snake_case` machine event name;
- `message`: short human-readable summary;
- `payload`: JSON object.

`schema_version` is optional for legacy records and is `1` for new records.
Secrets, tokens, private keys, and full environment values must never be logged.
Consumers ignore unknown fields and payload keys; changes to required fields
require a new schema version.
