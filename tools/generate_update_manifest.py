#!/usr/bin/env python3
"""
Ed25519 Signed Update Manifest Generator for Silicium Releases.
Produces a signed JSON update manifest for P2P and HTTP software distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.network_node import NodeConfig, NodeIdentity, sha256_bytes, stable_json


def build_default_config(export_dir: Path, identity_key_path: Path | None = None) -> NodeConfig:
    state_dir = export_dir / "state"
    export_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    return NodeConfig(
        export_dir=export_dir,
        roles={"compute"},
        node_id="publisher-node",
        idle_ms=10,
        once=True,
        max_items=0,
        p2p_gateway="",
        state_dir=state_dir,
        solana_enable=False,
        solana_rpc="",
        solana_program_id="",
        solana_wallet="",
        solana_bridge=export_dir / "bridge.cjs",
        solana_timeout_s=10,
        max_retries=0,
        bootstrap_worker=False,
        gossip_enable=False,
        gossip_bind="127.0.0.1",
        gossip_port=0,
        peer_http_bind="127.0.0.1",
        peer_http_port=0,
        peer_advertise_host="",
        peer_advertise_port=0,
        gossip_advertise_host="",
        gossip_advertise_port=0,
        seed_peers=[],
        mesh_key="",
        peer_sync_interval_s=10,
        peer_event_limit=64,
        peer_stale_after_s=60,
        relay_enable=False,
        relay_hops=1,
        identity_key_path=str(identity_key_path) if identity_key_path else "",
        reputation_score=0.0,
        replication_factor=0,
        replication_quorum=0,
        discovery_seeds=[],
        discovery_sync_interval_s=60,
        remote_dispatch_enable=False,
        remote_dispatch_limit=3,
        pull_tasks_enable=False,
        pull_tasks_interval_s=2,
        nat_punch_enable=False,
        solana_reputation_enable=False,
        solana_reputation_refresh_s=300,
        scheduler_onchain_weight=0.3,
        scheduler_offchain_weight=0.7,
        scheduler_capacity_weight=0.5,
    )


def create_signed_update_manifest(
    channel: str,
    version: str,
    artifact_path: Path,
    artifact_url: str,
    identity: NodeIdentity,
    check_interval_seconds: int = 300,
) -> dict[str, Any]:
    if channel not in {"dev", "prod"}:
        raise ValueError("invalid_channel")
    if not artifact_path.is_file():
        raise FileNotFoundError(f"artifact_not_found:{artifact_path}")

    data = artifact_path.read_bytes()
    digest = sha256_bytes(data)
    size_bytes = len(data)

    unsigned_payload = {
        "schema_version": 1,
        "channel": channel,
        "version": version,
        "content_id": digest,
        "sha256": digest,
        "url": artifact_url,
        "size_bytes": size_bytes,
        "check_interval_seconds": check_interval_seconds,
        "publisher_id": identity.identity_id,
        "publisher_public_key": identity.public_key_b64,
    }

    message_bytes = stable_json(unsigned_payload).encode("utf-8")
    signature = identity.sign_bytes(message_bytes)

    return {
        **unsigned_payload,
        "signature": signature,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Ed25519 signed update manifest")
    parser.add_argument("--channel", choices=["dev", "prod"], default="dev")
    parser.add_argument("--version", required=True, help="Version string (e.g. 0.3.0)")
    parser.add_argument("--artifact", required=True, type=Path, help="Path to artifact file")
    parser.add_argument("--url", required=True, help="Public download URL for artifact")
    parser.add_argument("--out", type=Path, help="Output JSON manifest file path")
    parser.add_argument("--export-dir", type=Path, default=Path(".silicium/publisher_export"))
    parser.add_argument("--key", type=Path, help="Path to Ed25519 private key PEM file")

    args = parser.parse_args()

    config = build_default_config(args.export_dir, args.key)
    identity = NodeIdentity(config)

    manifest = create_signed_update_manifest(
        channel=args.channel,
        version=args.version,
        artifact_path=args.artifact,
        artifact_url=args.url,
        identity=identity,
    )

    encoded = json.dumps(manifest, indent=2, ensure_ascii=True)
    if args.out:
        args.out.write_text(encoded + "\n", encoding="utf-8")
        print(f"Update manifest generated: {args.out}")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
