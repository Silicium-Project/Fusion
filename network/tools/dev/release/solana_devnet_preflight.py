#!/usr/bin/env python3
"""Verify the deployed Solana program through read-only Devnet RPC calls."""

from __future__ import annotations

import argparse
import json
from typing import Any
import urllib.error
import urllib.request


DEFAULT_RPC = "https://api.devnet.solana.com"
DEFAULT_PROGRAM_ID = "64Jj7p4MESFndrvB2PNGre4jehyPCF8PYrRyk93FAXCG"


def rpc_call(rpc_url: str, method: str, params: list[Any] | None = None) -> Any:
    request_body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=request_body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("solana_rpc_invalid_response")
    if payload.get("error") is not None:
        raise RuntimeError(f"solana_rpc_error:{payload['error']}")
    return payload.get("result")


def build_report(rpc_url: str, program_id: str) -> dict[str, Any]:
    version = rpc_call(rpc_url, "getVersion")
    slot = rpc_call(rpc_url, "getSlot", [{"commitment": "confirmed"}])
    account_result = rpc_call(
        rpc_url,
        "getAccountInfo",
        [program_id, {"encoding": "base64", "commitment": "confirmed"}],
    )
    account = account_result.get("value") if isinstance(account_result, dict) else None
    program_account = {
        "present": isinstance(account, dict),
        "executable": bool(account.get("executable")) if isinstance(account, dict) else False,
        "owner": str(account.get("owner", "")) if isinstance(account, dict) else "",
        "lamports": int(account.get("lamports", 0) or 0) if isinstance(account, dict) else 0,
        "space": int(account.get("space", 0) or 0) if isinstance(account, dict) else 0,
    }
    verified = bool(program_account["present"] and program_account["executable"])
    return {
        "schema_version": 1,
        "verified": verified,
        "rpc_url": rpc_url,
        "program_id": program_id,
        "slot": int(slot or 0),
        "version": version if isinstance(version, dict) else {"raw": version},
        "program_account": program_account,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="solana_devnet_preflight", description=__doc__)
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--program-id", default=DEFAULT_PROGRAM_ID)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        report = build_report(str(args.rpc).rstrip("/"), str(args.program_id).strip())
    except (OSError, urllib.error.URLError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"verified": False, "error": f"{type(exc).__name__}:{exc}"}, indent=2))
        return 2
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        account = report["program_account"]
        print(f"RPC: {report['rpc_url']}")
        print(f"Slot: {report['slot']}")
        print(f"Program: {report['program_id']}")
        print(f"Executable: {account['executable']}")
        print(f"Owner: {account['owner']}")
        print("Status: VERIFIED" if report["verified"] else "Status: NOT VERIFIED")
    return 0 if report["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
