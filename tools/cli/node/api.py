"""`node` commands that talk to a running node: submit tasks and requests,
read state, Solana worker bootstrap and job helpers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

from tools.cli.constants import REPO_ROOT
from tools.cli.context import Context, _resolve_mcp_settings


def _json_arg(raw: str, *, default: Any = None) -> Any:
    value = str(raw or "").strip()
    if not value:
        return default
    if value.startswith("@"):
        return json.loads(Path(value[1:]).expanduser().read_text(encoding="utf-8"))
    return json.loads(value)


def _node_export_dir(settings: Mapping[str, Any]) -> Path:
    return Path(str(settings["export_dir"])).expanduser()


def _node_solana_request(args: argparse.Namespace, op: str, params: Mapping[str, Any]) -> dict[str, Any]:
    bridge = Path(str(args.solana_bridge)).expanduser().resolve()
    request = {
        "op": op,
        "rpc_url": str(args.solana_rpc),
        "program_id": str(args.solana_program_id),
        "wallet_path": str(args.solana_wallet),
        "params": dict(params),
    }
    completed = subprocess.run(
        ["node", str(bridge)],
        input=json.dumps(request, separators=(",", ":"), ensure_ascii=True),
        text=True,
        capture_output=True,
        timeout=max(1, int(args.solana_timeout_s)),
        check=False,
    )
    raw = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    payload = json.loads(raw) if raw else {}
    if completed.returncode != 0 or payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or completed.stderr.strip() or "solana_bridge_failed"))
    return payload


def configure_node_submit_task(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-dir", default="", help="MCP/network export directory.")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--task", required=True, help="JSON object, or @file.json.")
    parser.add_argument("--roles", default="", help="Comma-separated required roles.")
    parser.add_argument("--priority", default="normal", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-ref", default="", help="JSON P2P ref, or @file.json.")
    parser.add_argument("--on-chain", default="", help="JSON on-chain accounts, or @file.json.")


def cmd_node_submit_task(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    from tools.mcp_server import McpTaskStore

    payload: dict[str, Any] = {"task": _json_arg(args.task, default={}), "priority": args.priority}
    if args.task_id:
        payload["task_id"] = args.task_id
    if args.roles:
        payload["required_roles"] = [item.strip() for item in str(args.roles).split(",") if item.strip()]
    p2p_ref = _json_arg(args.p2p_ref, default=None)
    if p2p_ref is not None:
        payload["p2p_ref"] = p2p_ref
    on_chain = _json_arg(args.on_chain, default=None)
    if on_chain is not None:
        payload["on_chain"] = on_chain
    print(json.dumps({"ok": True, **McpTaskStore(Path(settings["export_dir"])).submit(payload)}, indent=2, sort_keys=True))


def configure_node_submit_request(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-dir", default="", help="MCP/network export directory.")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--kind", required=True, choices=["audit", "resource", "challenge", "replicate", "retrieve", "pin", "unpin", "health"])
    parser.add_argument("--request", default="{}", help="JSON object, or @file.json.")
    parser.add_argument("--roles", default="", help="Comma-separated target roles.")
    parser.add_argument("--priority", default="high", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-ref", default="", help="JSON P2P ref, or @file.json.")
    parser.add_argument("--on-chain", default="", help="JSON on-chain accounts, or @file.json.")


def cmd_node_submit_request(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    from tools.mcp_server import McpRequestStore

    payload: dict[str, Any] = {"kind": args.kind, "request": _json_arg(args.request, default={}), "priority": args.priority}
    if args.request_id:
        payload["request_id"] = args.request_id
    if args.roles:
        payload["target_roles"] = [item.strip() for item in str(args.roles).split(",") if item.strip()]
    p2p_ref = _json_arg(args.p2p_ref, default=None)
    if p2p_ref is not None:
        payload["p2p_ref"] = p2p_ref
    on_chain = _json_arg(args.on_chain, default=None)
    if on_chain is not None:
        payload["on_chain"] = on_chain
    print(json.dumps({"ok": True, **McpRequestStore(Path(settings["export_dir"])).submit(payload)}, indent=2, sort_keys=True))


def configure_node_get(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-dir", default="", help="MCP/network export directory.")
    parser.add_argument("item_id")


def cmd_node_get_task(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((Path(settings["export_dir"]) / "tasks" / f"{args.item_id}.json").read_text(encoding="utf-8"))


def cmd_node_get_request(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((Path(settings["export_dir"]) / "requests" / f"{args.item_id}.json").read_text(encoding="utf-8"))


def cmd_node_get_result(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((Path(settings["export_dir"]) / f"result.{args.item_id}.json").read_text(encoding="utf-8"))


def configure_node_get_local_file(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--export-dir", default="", help="MCP/network export directory.")
    parser.add_argument("--node-id", required=True)


def cmd_node_get_heartbeat(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((_node_export_dir(settings) / f"node.{args.node_id}.heartbeat.json").read_text(encoding="utf-8"))


def cmd_node_get_metrics(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((_node_export_dir(settings) / f"node.{args.node_id}.metrics.json").read_text(encoding="utf-8"))


def cmd_node_get_peers(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    print((_node_export_dir(settings) / f"node.{args.node_id}.peers.json").read_text(encoding="utf-8"))


def configure_node_solana_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--solana-rpc", default=os.environ.get("SILICIUM_SOLANA_RPC", "https://api.devnet.solana.com"))
    parser.add_argument(
        "--solana-program-id",
        default=os.environ.get("SILICIUM_SOLANA_PROGRAM_ID", "A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2"),
    )
    parser.add_argument("--solana-wallet", default=os.environ.get("SILICIUM_SOLANA_WALLET", os.path.expanduser("~/.config/solana/id.json")))
    parser.add_argument("--solana-bridge", default=os.environ.get("SILICIUM_SOLANA_BRIDGE", str(REPO_ROOT / "tools" / "solana_layer_bridge.cjs")))
    parser.add_argument("--solana-timeout-s", type=int, default=int(os.environ.get("SILICIUM_SOLANA_TIMEOUT_S", "45")))


def configure_node_bootstrap_worker(parser: argparse.ArgumentParser) -> None:
    configure_node_solana_common(parser)


def cmd_node_bootstrap_worker(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    print(json.dumps(_node_solana_request(args, "register_worker", {}), indent=2, sort_keys=True))


def configure_node_fetch_job(parser: argparse.ArgumentParser) -> None:
    configure_node_solana_common(parser)
    parser.add_argument("--job", required=True)


def cmd_node_fetch_job(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    print(json.dumps(_node_solana_request(args, "fetch_job", {"job": args.job}), indent=2, sort_keys=True))


def configure_node_fetch_fragment(parser: argparse.ArgumentParser) -> None:
    configure_node_solana_common(parser)
    parser.add_argument("--fragment", default="")
    parser.add_argument("--job", default="")
    parser.add_argument("--fragment-index", type=int, default=-1)


def cmd_node_fetch_fragment(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    params: dict[str, Any] = {}
    if args.fragment:
        params["fragment"] = args.fragment
    else:
        params["job"] = args.job
        params["fragment_index"] = int(args.fragment_index)
    print(json.dumps(_node_solana_request(args, "fetch_fragment", params), indent=2, sort_keys=True))


def configure_node_create_job(parser: argparse.ArgumentParser) -> None:
    configure_node_solana_common(parser)
    parser.add_argument("--export-dir", default="", help="MCP/network export directory.")
    parser.add_argument("--mint", required=True)
    parser.add_argument("--client-token", required=True)
    parser.add_argument("--escrow-keypair-path", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--expected-fragments", type=int, required=True)
    parser.add_argument("--reward-per-fragment", required=True)
    parser.add_argument("--verifier-reward-per-vote", default="0")
    parser.add_argument("--verifier-reward-budget", default="0")
    parser.add_argument("--deadline-unix", required=True)
    parser.add_argument("--fragment-quorum", type=int, default=1)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--task", default="", help="Optional JSON object, or @file.json, to enqueue after job creation.")
    parser.add_argument("--roles", default="compute", help="Comma-separated roles for the optional task.")
    parser.add_argument("--priority", default="normal", choices=["low", "normal", "high", "urgent"])
    parser.add_argument("--p2p-ref", default="", help="Optional JSON P2P ref for the optional task.")
    parser.add_argument("--fragment-index", type=int, default=0, help="Fragment index for the optional compute task.")
    parser.add_argument("--worker-token", default="", help="Worker token account for the optional compute task.")
    parser.add_argument("--on-chain", default="", help="Optional extra JSON merged into the generated on_chain payload.")


def cmd_node_create_job(args: argparse.Namespace, ctx: Context) -> None:
    (void := ctx)
    settings = _resolve_mcp_settings(args)
    created = _node_solana_request(
        args,
        "create_job",
        {
            "mint": args.mint,
            "client_token": args.client_token,
            "escrow_keypair_path": args.escrow_keypair_path,
            "job_id": args.job_id,
            "expected_fragments": int(args.expected_fragments),
            "reward_per_fragment": args.reward_per_fragment,
            "verifier_reward_per_vote": args.verifier_reward_per_vote,
            "verifier_reward_budget": args.verifier_reward_budget,
            "deadline_unix": args.deadline_unix,
            "fragment_quorum": int(args.fragment_quorum),
        },
    )
    payload: dict[str, Any] = {"job": created}
    task_raw = str(args.task or "").strip()
    if task_raw:
        from tools.mcp_server import McpTaskStore

        task = _json_arg(task_raw, default={})
        extra_on_chain = _json_arg(args.on_chain, default={}) or {}
        on_chain = {
            "job": created.get("accounts", {}).get("job"),
            "fragment_index": int(args.fragment_index),
            "worker_token": args.worker_token,
            **extra_on_chain,
        }
        submit_payload: dict[str, Any] = {
            "task": task,
            "priority": args.priority,
            "required_roles": [item.strip() for item in str(args.roles).split(",") if item.strip()],
            "on_chain": on_chain,
        }
        if args.task_id:
            submit_payload["task_id"] = args.task_id
        p2p_ref = _json_arg(args.p2p_ref, default=None)
        if p2p_ref is not None:
            submit_payload["p2p_ref"] = p2p_ref
        payload["task"] = McpTaskStore(_node_export_dir(settings)).submit(submit_payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
