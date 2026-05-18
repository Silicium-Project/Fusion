#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD_COMPOSE = REPO_ROOT / "infra" / "docker-compose.world.yml"
DEFAULT_WORLD = "team-europe"
DEFAULT_RPC = "https://api.devnet.solana.com"
DEFAULT_PROGRAM_ID = "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"
DEFAULT_WALLET = "/state/solana/id.json"
NODE_SERVICE = "silicium-world-node"
NODE_UUID_SHIM = "/workspace/tools/node_uuid_cjs_shim.cjs"


def _base_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "SILICIUM_WORLD_NAME": args.world,
            "SILICIUM_NODE_ID": args.node_id,
            "SILICIUM_WORLD_SEEDS": args.seed,
            "SILICIUM_WORLD_ADVERTISE_HOST": args.advertise_host,
            "SILICIUM_NODE_ROLES": args.roles,
            "SILICIUM_SOLANA_ENABLE": "1" if args.solana else "0",
            "SILICIUM_SOLANA_RPC": args.rpc,
            "SILICIUM_SOLANA_PROGRAM_ID": args.program_id,
            "SILICIUM_SOLANA_WALLET": args.wallet,
        }
    )
    return env


def compose_command(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(WORLD_COMPOSE), *args]


def node_command(*args: str) -> list[str]:
    return compose_command("exec", NODE_SERVICE, "python3", "/workspace/silicium", *args)


def _run(cmd: Sequence[str], *, env: Mapping[str, str] | None = None) -> int:
    completed = subprocess.run(
        list(cmd),
        cwd=REPO_ROOT,
        env=dict(env or os.environ.copy()),
        check=False,
    )
    return int(completed.returncode)


def cmd_up(args: argparse.Namespace) -> int:
    return _run(compose_command("up", "--build", "-d"), env=_base_env(args))


def cmd_down(args: argparse.Namespace) -> int:
    return _run(compose_command("down"), env=_base_env(args))


def cmd_ps(args: argparse.Namespace) -> int:
    return _run(compose_command("ps"), env=_base_env(args))


def cmd_peers(args: argparse.Namespace) -> int:
    return _run(
        node_command(
            "node",
            "get-peers",
            "--export-dir",
            "/state/export",
            "--node-id",
            args.node_id,
        ),
        env=_base_env(args),
    )


def cmd_heartbeat(args: argparse.Namespace) -> int:
    return _run(
        node_command(
            "node",
            "get-heartbeat",
            "--export-dir",
            "/state/export",
            "--node-id",
            args.node_id,
        ),
        env=_base_env(args),
    )


def cmd_bootstrap_worker(args: argparse.Namespace) -> int:
    return _run(
        node_command(
            "node",
            "bootstrap-worker",
            "--solana-rpc",
            args.rpc,
            "--solana-program-id",
            args.program_id,
            "--solana-wallet",
            args.wallet,
        ),
        env=_base_env(args),
    )


def cmd_chain_smoke(args: argparse.Namespace) -> int:
    task_json = getattr(args, "task", "") or '{"kind":"compute","payload":"hello-chain"}'
    json.loads(task_json)
    shell = (
        "cd /workspace/solana-layer && "
        f"NODE_OPTIONS=--require={NODE_UUID_SHIM} "
        f"ANCHOR_WALLET={args.wallet} "
        f"SOLANA_RPC_URL={args.rpc} "
        f"SOLANA_LAYER_PROGRAM_ID={args.program_id} "
        f"SILICIUM_CHAIN_TASK_JSON={_shell_quote(task_json)} "
        "NO_DNA=1 npx ts-node scripts/devnet_minimal_job_flow.ts"
    )
    return _run(compose_command("exec", NODE_SERVICE, "sh", "-lc", shell), env=_base_env(args))


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--world", default=DEFAULT_WORLD)
    parser.add_argument("--node-id", default=os.environ.get("SILICIUM_NODE_ID", "node-1"))
    parser.add_argument("--seed", default=os.environ.get("SILICIUM_WORLD_SEEDS", ""))
    parser.add_argument("--advertise-host", default=os.environ.get("SILICIUM_WORLD_ADVERTISE_HOST", ""))
    parser.add_argument("--roles", default=os.environ.get("SILICIUM_NODE_ROLES", "compute,verify,storage,audit,resource"))
    parser.add_argument("--solana", action="store_true", default=os.environ.get("SILICIUM_SOLANA_ENABLE", "0") == "1")
    parser.add_argument("--rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", DEFAULT_RPC))
    parser.add_argument("--program-id", default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", DEFAULT_PROGRAM_ID))
    parser.add_argument("--wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", DEFAULT_WALLET))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-command Docker wrapper for a portable Silicium world node."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text, func in [
        ("up", "Build and start the world node.", cmd_up),
        ("down", "Stop the world node.", cmd_down),
        ("ps", "Show world compose status.", cmd_ps),
        ("peers", "Print the current peer table.", cmd_peers),
        ("heartbeat", "Print the current node heartbeat.", cmd_heartbeat),
        ("bootstrap-worker", "Register or confirm the Docker wallet worker on-chain.", cmd_bootstrap_worker),
        ("chain-smoke", "Run the Devnet minimal on-chain compute flow inside Docker.", cmd_chain_smoke),
        ("run-chain-task", "Run a packaged Devnet on-chain compute flow for a task JSON payload.", cmd_chain_smoke),
    ]:
        child = subparsers.add_parser(name, help=help_text)
        _add_common(child)
        if name in {"chain-smoke", "run-chain-task"}:
            child.add_argument("--task", default="", help="Task JSON payload hashed into the on-chain fragment result.")
        child.set_defaults(func=func)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
