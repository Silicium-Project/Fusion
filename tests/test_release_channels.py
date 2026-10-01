from __future__ import annotations

import json
from pathlib import Path

from tests.network_node_support import _config
from tools import network_node


def test_peer_registry_isolated_by_release_channel(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "dev", "dev-node", release_channel="dev"), tmp_path / "dev")
    assert peer._record_peer(
        {
            "node_id": "dev-node",
            "release_channel": "dev",
            "roles": ["compute"],
            "timestamp_utc": network_node.utc_now(),
        }
    ) is True
    payload = {
        "node_id": "prod-node",
        "release_channel": "prod",
        "roles": ["compute"],
        "timestamp_utc": network_node.utc_now(),
    }

    assert peer._record_peer(payload) is False
    snapshot = peer.peers_snapshot(persist=False)
    assert [item["node_id"] for item in snapshot["peers"]] == ["dev-node"]
    assert snapshot["release_channel"] == "dev"
    assert snapshot["release_channels"] == {"dev": 1}


def test_update_announcement_cannot_cross_channel(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "dev", "dev-node", release_channel="dev"), tmp_path / "dev")
    digest = network_node.sha256_bytes(b"prod-update")
    release = {
        "channel": "prod",
        "version": "1.0.0",
        "platform": "linux-x86_64",
        "url": "https://example.invalid/prod.AppImage",
        "sha256": digest,
        "content_id": digest,
        "size_bytes": len(b"prod-update"),
        "check_interval_seconds": 3600,
        "signature": "test-signature",
    }

    assert peer._record_update_announcement(release, "prod-node") is False
    assert peer.update_announcements() == []

    announcement_dir = peer.update_announcements_dir / "prod"
    announcement_dir.mkdir(parents=True, exist_ok=True)
    (announcement_dir / "stale.json").write_text(json.dumps(release), encoding="utf-8")
    assert peer.update_announcements() == []


def test_task_control_cannot_cross_channel(tmp_path: Path) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "dev", "dev-node", release_channel="dev"))
    control = {
        "root_job_id": "job-1",
        "control_id": "control-1",
        "action": "cancel",
        "issuer_node_id": "orchestrator-1",
        "release_channel": "prod",
    }

    assert node.validate_task_control(control, signed_by="orchestrator-1") is False
