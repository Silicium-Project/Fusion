#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
WORLD_COMPOSE = REPO_ROOT / "infra" / "docker-compose.world.yml"
DEFAULT_RPC = "https://api.devnet.solana.com"
DEFAULT_PROGRAM_ID = "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"
DEFAULT_WALLET = "/state/solana/id.json"
TOOLS_SERVICE = "silicium-world-solana"
NODE_SERVICE = "silicium-world-node"


def _compose_base(*, tools_profile: bool) -> list[str]:
    cmd = ["docker", "compose", "-f", str(WORLD_COMPOSE)]
    if tools_profile:
        cmd.extend(["--profile", "tools"])
    return cmd


def build_tools_command(*args: str) -> list[str]:
    return _compose_base(tools_profile=True) + [
        "run",
        "--rm",
        "--entrypoint",
        "/bin/sh",
        TOOLS_SERVICE,
        "-lc",
        " ".join(args),
    ]


def build_node_command(*args: str) -> list[str]:
    return _compose_base(tools_profile=False) + [
        "exec",
        NODE_SERVICE,
        "python3",
        "/workspace/silicium",
        *args,
    ]


def _run(cmd: Sequence[str]) -> int:
    completed = subprocess.run(
        list(cmd),
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        check=False,
    )
    return int(completed.returncode)


def cmd_init_wallet(args: argparse.Namespace) -> int:
    force = "--force " if args.force else ""
    shell = (
        f"mkdir -p {Path(args.wallet).parent.as_posix()} && "
        f"solana-keygen new --no-bip39-passphrase {force}--outfile {args.wallet}"
    )
    return _run(build_tools_command(shell))


def cmd_pubkey(args: argparse.Namespace) -> int:
    return _run(build_tools_command(f"solana-keygen pubkey {args.wallet}"))


def cmd_balance(args: argparse.Namespace) -> int:
    return _run(
        build_tools_command(
            f"solana balance --url {args.rpc} --keypair {args.wallet}"
        )
    )


def cmd_airdrop(args: argparse.Namespace) -> int:
    shell = (
        f"pubkey=$(solana-keygen pubkey {args.wallet}) && "
        f"solana airdrop {args.amount:g} \"$pubkey\" --url {args.rpc}"
    )
    return _run(build_tools_command(shell))


def cmd_bootstrap_worker(args: argparse.Namespace) -> int:
    return _run(
        build_node_command(
            "node",
            "bootstrap-worker",
            "--solana-rpc",
            args.rpc,
            "--solana-program-id",
            args.program_id,
            "--solana-wallet",
            args.wallet,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the world-mode Solana wallet entirely through Docker helpers."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_wallet = subparsers.add_parser(
        "init-wallet", help="Create the world wallet inside Docker-managed state."
    )
    init_wallet.add_argument(
        "--wallet",
        default=DEFAULT_WALLET,
        help="Wallet path inside the helper container.",
    )
    init_wallet.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing wallet file.",
    )
    init_wallet.set_defaults(func=cmd_init_wallet)

    pubkey = subparsers.add_parser(
        "pubkey", help="Print the public key of the Docker-managed world wallet."
    )
    pubkey.add_argument("--wallet", default=DEFAULT_WALLET)
    pubkey.set_defaults(func=cmd_pubkey)

    balance = subparsers.add_parser(
        "balance", help="Check the Devnet balance of the Docker-managed world wallet."
    )
    balance.add_argument("--wallet", default=DEFAULT_WALLET)
    balance.add_argument("--rpc", default=DEFAULT_RPC)
    balance.set_defaults(func=cmd_balance)

    airdrop = subparsers.add_parser(
        "airdrop", help="Request Devnet SOL for the Docker-managed world wallet."
    )
    airdrop.add_argument("amount", type=float, nargs="?", default=2.0)
    airdrop.add_argument("--wallet", default=DEFAULT_WALLET)
    airdrop.add_argument("--rpc", default=DEFAULT_RPC)
    airdrop.set_defaults(func=cmd_airdrop)

    bootstrap_worker = subparsers.add_parser(
        "bootstrap-worker",
        help="Register the current Docker-managed world wallet as an on-chain worker.",
    )
    bootstrap_worker.add_argument("--wallet", default=DEFAULT_WALLET)
    bootstrap_worker.add_argument("--rpc", default=DEFAULT_RPC)
    bootstrap_worker.add_argument("--program-id", default=DEFAULT_PROGRAM_ID)
    bootstrap_worker.set_defaults(func=cmd_bootstrap_worker)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
