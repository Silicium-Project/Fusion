"""Discovery of worker capacity from the emitter's peer snapshot.

The local emitter node writes the peers it knows to
`node.<node_id>.peers.json` in the export directory. The orchestrator reads it
to size its in-flight limits and to decide whether a verifier other than the
compute node exists.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable


def discovered_role_capacity(
    export_dir: Path,
    node_id: str,
    role: str,
    required_features: Iterable[str] = (),
) -> int:
    """Count currently discovered HTTP peers that advertise a workload role."""
    peers_path = export_dir / f"node.{node_id}.peers.json"
    try:
        payload = json.loads(peers_path.read_text(encoding="utf-8")) if peers_path.exists() else {}
    except json.JSONDecodeError:
        payload = {}
    peers = payload.get("peers", []) if isinstance(payload, dict) else []
    wanted = role.strip().lower()
    wanted_features = {str(feature).strip() for feature in required_features if str(feature).strip()}
    eligible = {
        str(peer.get("node_id", "")).strip()
        for peer in peers
        if isinstance(peer, dict)
        and wanted
        in {
            str(value).strip().lower()
            for value in (peer.get("roles", []) if isinstance(peer.get("roles"), list) else [])
        }
        and str(peer.get("http_base_url", "")).strip()
        and str(peer.get("node_id", "")).strip()
        and wanted_features.issubset(
            {str(feature).strip() for feature in (peer.get("features", []) if isinstance(peer.get("features"), list) else [])}
        )
    }
    # Never report zero: an empty network still runs with one task in flight.
    return max(1, len(eligible))


def resolve_in_flight_limit(configured: int, export_dir: Path, node_id: str, role: str) -> int:
    """Configured limit when positive, otherwise the discovered capacity for `role`."""
    return max(1, configured) if configured > 0 else discovered_role_capacity(export_dir, node_id, role)


def wait_for_network_role(export_dir: Path, node_id: str, role: str, timeout_s: float = 20.0) -> None:
    """Block until a peer advertising `role` with an HTTP URL appears; TimeoutError otherwise."""
    peers_path = export_dir / f"node.{node_id}.peers.json"
    deadline = time.monotonic() + timeout_s
    wanted = role.lower()
    while time.monotonic() <= deadline:
        try:
            payload = json.loads(peers_path.read_text(encoding="utf-8")) if peers_path.exists() else {}
        except json.JSONDecodeError:
            payload = {}
        peers = payload.get("peers", []) if isinstance(payload, dict) else []
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            roles = {str(item).lower() for item in peer.get("roles", []) if str(item).strip()}
            if wanted in roles and str(peer.get("http_base_url", "")).strip():
                return
        time.sleep(0.25)
    raise TimeoutError(f"missing network peer with role {role!r} after {timeout_s:.1f}s: {peers_path}")
