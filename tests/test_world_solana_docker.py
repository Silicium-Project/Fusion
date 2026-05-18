from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "world_solana_docker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("world_solana_docker", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_tools_command_uses_docker_compose_helper_service() -> None:
    module = _load_module()
    cmd = module.build_tools_command("solana-keygen pubkey /state/solana/id.json")

    assert cmd[:6] == [
        "docker",
        "compose",
        "-f",
        str(module.WORLD_COMPOSE),
        "--profile",
        "tools",
    ]
    assert "run" in cmd
    assert module.TOOLS_SERVICE in cmd
    assert cmd[-1] == "solana-keygen pubkey /state/solana/id.json"


def test_build_node_command_targets_world_node_bootstrap_worker() -> None:
    module = _load_module()
    cmd = module.build_node_command(
        "node",
        "bootstrap-worker",
        "--solana-rpc",
        module.DEFAULT_RPC,
    )

    assert cmd[:4] == ["docker", "compose", "-f", str(module.WORLD_COMPOSE)]
    assert module.NODE_SERVICE in cmd
    assert "/workspace/silicium" in cmd
    assert cmd[-4:] == [
        "node",
        "bootstrap-worker",
        "--solana-rpc",
        module.DEFAULT_RPC,
    ]


def test_parser_defaults_keep_wallet_inside_state_volume() -> None:
    module = _load_module()
    parser = module.build_parser()
    args = parser.parse_args(["balance"])

    assert args.wallet == "/state/solana/id.json"
    assert args.rpc == "https://api.devnet.solana.com"
