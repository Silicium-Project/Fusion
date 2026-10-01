"""Silicium MCP/HTTP ingress server (legacy Python runtime).

Authenticated HTTP server that accepts tasks and post-job requests into the
durable queues of the export directory, serves worker resources and exposes
an MCP (JSON-RPC over Streamable HTTP) endpoint. Entry point:
``tools/mcp_server.py`` (script, ``python -m tools.mcp_server``, or
``silicium mcp serve``), which re-exports the public names of this package.

Layout (one module per responsibility):

- constants.py        resource URIs, tool names, vocabularies, HTTP constants
- validation.py       envelope field normalisation (ids, roles, priority, p2p_ref)
- persistence.py      compact JSON, atomic writes, NDJSON appends, UTC clock
- access_policy.py    tool/resource allow and deny lists
- export_store.py     resource URI -> export file, with snapshot fallback
- task_store.py       task ingress (tasks/*.json + task queues)
- request_store.py    request inbox (requests/*.json + request queues)
- snapshot_store.py   persistent resource snapshots with retention, bundles
- control_plane.py    control.request.json (interrupt, runner mode)
- metrics.py          Prometheus counters
- observability.py    structured logger + metrics bundle
- app.py              McpHttpApp: shared state and tool execution
- http_io.py          JSON request/response helpers
- discovery.py        OAuth discovery stub and OpenAPI document
- tool_catalog.py     MCP tool descriptors and resource templates
- auth.py             bearer-token check (handler mixin)
- handler_observe.py  access log/metrics hooks (handler mixin)
- handler_get.py      GET routes (handler mixin)
- handler_post.py     POST routes (handler mixin)
- handler_mcp.py      POST /mcp JSON-RPC transport (handler mixin)
- mcp_methods.py      MCP methods: initialize, resources/*, tools/* (handler mixin)
- handler.py          McpHttpHandler assembled from the mixins
- cli.py              argument parser and main()

Submodules are imported explicitly (``from tools.mcp_ingress.task_store import
McpTaskStore``); this file deliberately imports nothing so that light users
such as the task store do not load the HTTP stack.
"""
