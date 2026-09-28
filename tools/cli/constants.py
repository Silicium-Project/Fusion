"""Paths, defaults and choice lists shared by every command.
"""

from __future__ import annotations

from pathlib import Path

# tools/cli/constants.py -> Network/
REPO_ROOT = Path(__file__).resolve().parents[2]


WORKLOAD_ROOT = REPO_ROOT / "workloads"


WORKLOAD_SCHEMA_FILE = WORKLOAD_ROOT / "schema" / "workload-manifest-v2.schema.json"


WORKLOAD_FIXTURES_DIR = WORKLOAD_ROOT / "fixtures"


WORKLOAD_FIXTURES_INDEX = WORKLOAD_FIXTURES_DIR / "fixtures.json"


WORKLOAD_ALIGNMENT_POLICY = WORKLOAD_FIXTURES_DIR / "alignment-policy.json"


WORKLOAD_GOLDEN_CORPUS_FILE = WORKLOAD_ROOT / "golden" / "golden-corpus.json"


PERF_BUDGET_FILE = REPO_ROOT / "docs" / "development" / "performance-budgets.json"


POSIX_PYTEST_IMAGE_DEFAULT = "python:3.12-bookworm"


LEDGER_SUFFIX = {
    "localnet": "local-ledger",
    "devnet": "devnet-ledger",
    "testnet": "testnet-ledger",
    "mainnet": "mainnet-ledger",
}


LEDGER_NETWORKS = sorted(LEDGER_SUFFIX.keys())


START_TARGETS = {
    "localnet": ("silicium-localnet", None),
    "devnet": ("silicium-devnet", "devnet"),
    "testnet": ("silicium-node", None),
    "mainnet": ("silicium-mainnet", "mainnet"),
    "proxy": ("silicium-proxy", "proxy"),
    "proxy-smoke": ("proxy-smoke-target", "smoke"),
}


START_CHOICES = sorted(START_TARGETS.keys())


SERVICE_MAP: dict[str, tuple[str, str | None]] = {}


for alias, (svc, profile) in START_TARGETS.items():
    SERVICE_MAP[alias] = (svc, profile)
    SERVICE_MAP[svc] = (svc, profile)


# Explicit compose service name
SERVICE_MAP["proxy-smoke-target"] = START_TARGETS["proxy-smoke"]


LOG_CHOICES = sorted(SERVICE_MAP.keys())


HISTORY_FILE = Path.home() / ".silicium_history"


COMPOSE_FILE = REPO_ROOT / "infra" / "docker-compose.yml"


COMPOSE_ENV_FILE = REPO_ROOT / "infra" / ".env"


LOCAL_STATE_DIR = REPO_ROOT / ".silicium"


DEFAULT_CONFIG_FILE = LOCAL_STATE_DIR / "config.json"


SERVICE_CHOICES = sorted(
    {
        "silicium-localnet",
        "silicium-devnet",
        "silicium-node",
        "silicium-mainnet",
        "silicium-proxy",
        "proxy-smoke-target",
    }
)


TOP_LEVEL_COMMANDS = [
    "test",
    "check",
    "doctor",
    "budget",
    "smoke",
    "setup",
    "clean",
    "ledger",
    "history",
    "workload",
    "start",
    "stop",
    "status",
    "logs",
    "exec",
    "alias",
    "tui",
    "shell",
    "mcp",
    "node",
    "help",
    "exit",
    "quit",
]


SUBCOMMANDS = {
    "setup": ["up", "down"],
    "ledger": ["list", "wipe", "export", "import"],
    "history": ["show", "clear"],
    "clean": ["cache", "ledgers", "all"],
    "workload": ["list", "show", "queue", "lint", "index", "fixtures", "alignment", "golden"],
    "mcp": ["serve", "print-config"],
    "node": ["start", "submit-task", "get-task", "get-result", "submit-request", "get-request", "create-job", "fetch-job", "fetch-fragment", "bootstrap-worker", "get-heartbeat", "get-metrics", "get-peers"],
}


SETUP_TARGET_CHOICES = ["localnet", "devnet", "testnet", "mainnet", "proxy"]


SETUP_DEFAULT_TARGETS = ["localnet", "proxy"]


WORKLOAD_TAXONOMY_CATEGORIES = ["calcul", "verification"]


WORKLOAD_TAXONOMY_DOMAINS = [
    "compression",
    "integrity",
    "math",
    "ml",
    "rendering",
    "simulation",
    "statistics",
    "video",
]


WORKLOAD_TAXONOMY_COMPLEXITIES = ["low", "medium", "high"]


WORKLOAD_TAXONOMY_RESOURCE_PROFILES = [
    "cpu_light",
    "cpu_heavy",
    "gpu_optional",
    "gpu_required",
    "memory_light",
    "memory_heavy",
]


WORKLOAD_TAXONOMY_DETERMINISM = [
    "deterministic",
    "bounded_stochastic",
    "stochastic",
]


WORKLOAD_TAXONOMY_TAGS = [
    "audit",
    "compression",
    "cpu",
    "deterministic",
    "embeddings",
    "gpu",
    "hash",
    "libm",
    "math",
    "ml",
    "monte_carlo",
    "non_deterministic",
    "rendering",
    "simulation",
    "spotcheck",
    "statistics",
    "stochastic",
    "transcoding",
    "verification",
]


TUI_FRONTENDS = {"textual", "curses", "headless"}


TUI_CONNECTORS = {"inprocess", "stdio", "http"}


MCP_DEFAULT_BIND = "127.0.0.1"


WORLD_DEFAULT_GOSSIP_PORT = 46000


WORLD_DEFAULT_PEER_HTTP_PORT = 46001


DEFAULT_PEER_SYNC_INTERVAL_S = 5


DEFAULT_PEER_STALE_AFTER_S = 15


WORLD_DEFAULT_PEER_SYNC_INTERVAL_S = 10


WORLD_DEFAULT_DISCOVERY_SYNC_INTERVAL_S = 15


DEFAULT_PUBLIC_STUN_SERVER = "stun.l.google.com:19302"


MCP_DEFAULT_PORT = 9765


MCP_DEFAULT_EXPORT_DIR = LOCAL_STATE_DIR / "mcp" / "export"


MCP_DEFAULT_TOKEN_FILE = LOCAL_STATE_DIR / "mcp" / "token"


CLI_STRUCTURED_LOG_DIR = LOCAL_STATE_DIR / "logs"


CLI_STRUCTURED_LOG_ENV = "SILICIUM_CLI_STRUCTURED_LOG"
