"""Protocol constants of the MCP/HTTP ingress server.

Resource URIs, tool names, the closed vocabularies accepted in task and
request envelopes, and the fixed HTTP paths/content types. Everything here is
part of the public contract described in docs/contracts/mcp-connector-spec.md,
so values must not change without updating that document.
"""

from __future__ import annotations

# --- Resource URIs -----------------------------------------------------------

RESOURCE_STATUS_CURRENT = "resources://silicium/status/current"
RESOURCE_REPORTS_RECENT = "resources://silicium/reports/recent"
RESOURCE_RESULT_PREFIX = "resources://silicium/results/by-task/"
RESOURCE_LOGS_PREFIX = "resources://silicium/logs/by-task/"
RESOURCE_TASK_PREFIX = "resources://silicium/tasks/by-id/"
RESOURCE_REQUEST_PREFIX = "resources://silicium/requests/by-id/"
RESOURCE_NODE_HEARTBEAT_PREFIX = "resources://silicium/nodes/heartbeat/"
RESOURCE_NODE_METRICS_PREFIX = "resources://silicium/nodes/metrics/"
RESOURCE_NODE_PEERS_PREFIX = "resources://silicium/nodes/peers/"

# --- JSON-RPC / MCP protocol ---------------------------------------------------

MCP_JSONRPC_VERSION = "2.0"
MCP_DEFAULT_PROTOCOL_VERSION = "2024-11-05"

# --- Tool names ----------------------------------------------------------------

TOOL_RUN_ACTION = "tools.silicium.run_action"
TOOL_INTERRUPT_ACTION = "tools.silicium.interrupt_action"
TOOL_SELECT_RUNNER_MODE = "tools.silicium.select_runner_mode"
TOOL_GET_HEALTH = "tools.silicium.get_health"
TOOL_SUBMIT_TASK = "tools.silicium.submit_task"
TOOL_GET_TASK = "tools.silicium.get_task"
TOOL_SUBMIT_REQUEST = "tools.silicium.submit_request"
TOOL_GET_REQUEST = "tools.silicium.get_request"

# Order matters: /resources/list and /tools/list return entries in this order.
SUPPORTED_RESOURCES = (
    RESOURCE_STATUS_CURRENT,
    RESOURCE_REPORTS_RECENT,
    "resources://silicium/results/by-task/{task_id}",
    "resources://silicium/logs/by-task/{task_id}",
    "resources://silicium/tasks/by-id/{task_id}",
    "resources://silicium/requests/by-id/{request_id}",
    "resources://silicium/nodes/heartbeat/{node_id}",
    "resources://silicium/nodes/metrics/{node_id}",
    "resources://silicium/nodes/peers/{node_id}",
)

SUPPORTED_TOOLS = (
    TOOL_RUN_ACTION,
    TOOL_INTERRUPT_ACTION,
    TOOL_SELECT_RUNNER_MODE,
    TOOL_GET_HEALTH,
    TOOL_SUBMIT_TASK,
    TOOL_GET_TASK,
    TOOL_SUBMIT_REQUEST,
    TOOL_GET_REQUEST,
)

# Runner modes accepted by TOOL_SELECT_RUNNER_MODE.
RUNNER_MODES = ("auto", "emu", "native", "dynamo")

# --- Envelope vocabularies -----------------------------------------------------

NETWORK_ROLES = frozenset({"compute", "verify", "storage", "audit", "resource"})
REQUEST_KINDS = frozenset({"audit", "resource", "challenge", "replicate", "retrieve", "pin", "unpin", "health"})
PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
P2P_PROTOCOLS = frozenset({"ipfs", "ipns", "libp2p", "http", "https", "file", "silicium"})

# Upper bound for request bodies and for encoded task/request envelopes.
MAX_ENVELOPE_BYTES = 256 * 1024

# --- HTTP ----------------------------------------------------------------------

METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
OAUTH_DISCOVERY_PATHS = (
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp",
    "/mcp/.well-known/oauth-authorization-server",
)
