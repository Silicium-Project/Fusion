"""Bridge to the Node.js Solana helper (tools/solana_layer_bridge.cjs)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from tools.node.config import NodeConfig


class SolanaBridge:
    """Call the Node.js Solana bridge as a subprocess (JSON over stdin/stdout)."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config

    def call(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run bridge operation ``op``; a disabled bridge returns a ``skipped`` result."""
        if not self.config.solana_enable:
            return {"ok": True, "enabled": False, "skipped": True, "op": op, "reason": "solana_disabled"}
        if not self.config.solana_program_id:
            raise ValueError("missing_solana_program_id")
        if not self.config.solana_wallet:
            raise ValueError("missing_solana_wallet")
        if not self.config.solana_bridge.exists():
            raise ValueError(f"missing_solana_bridge:{self.config.solana_bridge}")

        request = {
            "op": op,
            "rpc_url": self.config.solana_rpc,
            "program_id": self.config.solana_program_id,
            "wallet_path": self.config.solana_wallet,
            "params": params,
        }
        completed = subprocess.run(
            ["node", str(self.config.solana_bridge)],
            input=json.dumps(request, separators=(",", ":"), ensure_ascii=True),
            text=True,
            capture_output=True,
            timeout=max(1, self.config.solana_timeout_s),
            check=False,
        )
        raw = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"solana_bridge_bad_json:{completed.stdout}:{completed.stderr}") from exc
        if completed.returncode != 0 or payload.get("ok") is False:
            message = payload.get("error") or completed.stderr.strip() or "solana_bridge_failed"
            raise RuntimeError(str(message))
        return payload
