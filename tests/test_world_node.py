from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools" / "world_node.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("world_node", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compose_command_targets_world_compose_file() -> None:
    module = _load_module()

    assert module.compose_command("ps") == [
        "docker",
        "compose",
        "-f",
        str(module.WORLD_COMPOSE),
        "ps",
    ]


def test_node_command_executes_silicium_inside_world_node() -> None:
    module = _load_module()

    assert module.node_command("node", "get-peers") == [
        "docker",
        "compose",
        "-f",
        str(module.WORLD_COMPOSE),
        "exec",
        module.NODE_SERVICE,
        "python3",
        "/workspace/silicium",
        "node",
        "get-peers",
    ]


def test_up_parser_builds_self_contained_world_env() -> None:
    module = _load_module()
    parser = module.build_parser()
    args = parser.parse_args(
        [
            "up",
            "--node-id",
            "france-1",
            "--seed",
            "http://100.112.48.71:46001",
            "--advertise-host",
            "100.112.48.71",
            "--roles",
            "verify,storage,audit",
            "--solana",
        ]
    )

    env = module._base_env(args)

    assert env["SILICIUM_WORLD_NAME"] == "team-europe"
    assert env["SILICIUM_NODE_ID"] == "france-1"
    assert env["SILICIUM_WORLD_SEEDS"] == "http://100.112.48.71:46001"
    assert env["SILICIUM_WORLD_ADVERTISE_HOST"] == "100.112.48.71"
    assert env["SILICIUM_NODE_ROLES"] == "verify,storage,audit"
    assert env["SILICIUM_SOLANA_ENABLE"] == "1"
    assert env["SILICIUM_SOLANA_PROGRAM_ID"] == module.DEFAULT_PROGRAM_ID


def test_chain_smoke_command_runs_devnet_flow_in_container(monkeypatch) -> None:
    module = _load_module()
    captured: dict[str, object] = {}

    def fake_run(cmd, *, env=None):
        captured["cmd"] = list(cmd)
        captured["env"] = dict(env)
        return 0

    monkeypatch.setattr(module, "_run", fake_run)
    parser = module.build_parser()
    args = parser.parse_args(["chain-smoke", "--solana", "--node-id", "france-1"])

    assert module.cmd_chain_smoke(args) == 0

    cmd = captured["cmd"]
    assert cmd[:6] == ["docker", "compose", "-f", str(module.WORLD_COMPOSE), "exec", module.NODE_SERVICE]
    assert f"NODE_OPTIONS=--require={module.NODE_UUID_SHIM}" in cmd[-1]
    assert "scripts/devnet_minimal_job_flow.ts" in cmd[-1]
    assert module.DEFAULT_PROGRAM_ID in cmd[-1]
