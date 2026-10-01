"""Signed software-update announcements and manifests propagated over the mesh.

Covers announcement/artifact transfer across an isolated peer, platform
preservation, non-blocking publish acks, unsigned local probe publishing,
manifest anti-entropy and seeding the local manifest at startup.
"""

import json
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _config, _signed_json_request_status


def test_signed_update_announcement_and_artifact_cross_an_isolated_peer(tmp_path: Path) -> None:
    export_a = tmp_path / "update-source"
    export_b = tmp_path / "isolated-node"
    config_a = _config(export_a, "update-source")
    peer_a = network_node.PeerNetwork(config_a, export_a)
    peer_a.start()
    try:
        config_b = _config(export_b, "isolated-node", seed_peers=[f"127.0.0.1:{config_a.gossip_port}"])
        peer_b = network_node.PeerNetwork(config_b, export_b)
        peer_b.start()
        try:
            deadline = time.time() + 5.0
            while time.time() < deadline and peer_b.peers_snapshot()["count"] < 2:
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 2

            artifact = b"offline-update-artifact" * 4096
            digest = network_node.sha256_bytes(artifact)
            source_path = export_a / "p2p" / digest
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(artifact)
            unsigned = {
                "schema_version": 1,
                "channel": "dev",
                "version": "0.2.9-dev.99",
                "url": "https://vps-910c1dbc.vps.ovh.net/downloads/silicium-node-windows-dev.exe",
                "sha256": digest,
                "content_id": digest,
                "size_bytes": len(artifact),
                "check_interval_seconds": 30,
                "publisher_id": peer_a.identity.identity_id,
                "publisher_public_key": peer_a.identity.public_key_b64,
            }
            message_bytes = network_node.stable_json(unsigned).encode("utf-8")
            release = {
                **unsigned,
                "auto_install": True,
                "signature": peer_a.identity.sign_bytes(message_bytes),
                "signing_key_id": "test-key",
            }
            assert peer_a._record_update_announcement(release, "update-source")
            peer_a.publish("software_update", release)

            deadline = time.time() + 5.0
            while time.time() < deadline and not peer_b.update_announcements():
                time.sleep(0.05)
            announcements = peer_b.update_announcements()
            assert announcements[-1]["content_id"] == digest
            assert announcements[-1]["cached"] is False

            with urllib.request.urlopen(peer_b.http_base_url + "/updates/manifest", timeout=2) as response:
                manifest = json.loads(response.read().decode("utf-8"))
            assert manifest["source"] == "silicium-gossip"
            assert manifest["releases"][-1]["version"] == "0.2.9-dev.99"

            with urllib.request.urlopen(peer_b.http_base_url + f"/updates/content/{digest}", timeout=5) as response:
                assert response.read() == artifact
            assert (export_b / "p2p" / digest).read_bytes() == artifact
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_update_announcement_preserves_platform_for_client_selection() -> None:
    digest = network_node.sha256_bytes(b"linux-update")
    normalized = network_node.PeerNetwork._normalize_update_announcement(
        {
            "channel": "dev",
            "version": "0.2.9-dev.100",
            "platform": "linux-x86_64",
            "url": "https://vps-910c1dbc.vps.ovh.net/downloads/silicium-node-linux-dev.AppImage",
            "sha256": digest,
            "content_id": digest,
            "size_bytes": len(b"linux-update"),
            "signature": "signed-by-release-authority",
            "signing_key_id": "test-key",
        }
    )

    assert normalized is not None
    assert normalized["platform"] == "linux-x86_64"


def test_update_gossip_publish_ack_does_not_wait_for_slow_fanout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    export_target = tmp_path / "update-publish-target"
    export_signer = tmp_path / "update-publish-signer"
    target = network_node.PeerNetwork(_config(export_target, "update-target", gossip_enable=False), export_target)
    signer = network_node.PeerNetwork(_config(export_signer, "update-signer", gossip_enable=False), export_signer)
    broadcast_started = threading.Event()
    release_broadcast = threading.Event()

    def slow_broadcast(_message: dict, exclude: str = "") -> None:
        del exclude
        broadcast_started.set()
        release_broadcast.wait(timeout=2)

    monkeypatch.setattr(target, "_broadcast", slow_broadcast)
    target.start()
    try:
        digest = network_node.sha256_bytes(b"async-update")
        release = {
            "channel": "dev",
            "version": "0.2.9-dev.async",
            "url": "https://example.invalid/silicium-node-windows-dev.exe",
            "sha256": digest,
            "content_id": digest,
            "size_bytes": 12,
            "auto_install": True,
            "check_interval_seconds": 30,
            "signature": "signed-by-release-authority",
            "signing_key_id": "test-key",
        }
        started = time.monotonic()
        status, body = _signed_json_request_status(
            signer,
            target.http_base_url,
            "/gossip/publish",
            {"topic": "software_update", "payload": release},
        )
        elapsed = time.monotonic() - started

        assert status == 202
        assert body == {"ok": True, "topic": "software_update"}
        assert elapsed < 1.0
        assert broadcast_started.wait(timeout=1)
        assert target.update_announcements()[-1]["version"] == "0.2.9-dev.async"
    finally:
        release_broadcast.set()
        target.stop()


def test_local_node_probe_can_publish_without_peer_signature(tmp_path: Path) -> None:
    export_dir = tmp_path / "node-probe"
    peer = network_node.PeerNetwork(_config(export_dir, "probe-target", gossip_enable=False), export_dir)
    peer.start()
    try:
        payload = network_node.stable_json(
            {
                "topic": "node_probe",
                "payload": {
                    "probe_id": "local-test",
                    "status": "ok",
                    "resolved_addresses": ["127.0.0.1"],
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            peer.http_base_url + "/gossip/publish",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 202
            assert json.loads(response.read().decode("utf-8")) == {"ok": True, "topic": "node_probe"}
    finally:
        peer.stop()


def test_update_manifest_anti_entropy_recovers_a_missed_gossip_event(tmp_path: Path) -> None:
    export_a = tmp_path / "update-source"
    export_b = tmp_path / "late-peer"
    config_a = _config(export_a, "update-source", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    peer_a.start()
    try:
        artifact = b"durable-update-artifact" * 1024
        digest = network_node.sha256_bytes(artifact)
        source_path = export_a / "p2p" / digest
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(artifact)
        release = {
            "channel": "dev",
            "version": "0.2.9-dev.100",
            "url": "https://example.invalid/silicium-node-windows-dev.exe",
            "sha256": digest,
            "content_id": digest,
            "size_bytes": len(artifact),
            "auto_install": True,
            "check_interval_seconds": 30,
            "signature": "signed-by-release-authority",
            "signing_key_id": "test-key",
        }
        assert peer_a._record_update_announcement(release, "update-source")
        assert peer_a.recent_events(10) == []

        config_b = _config(
            export_b,
            "late-peer",
            gossip_enable=False,
            seed_peers=[peer_a.http_base_url],
        )
        peer_b = network_node.PeerNetwork(config_b, export_b)
        peer_b.start()
        try:
            peer_b.sync_once()
            announcements = peer_b.update_announcements()
            assert len(announcements) == 1
            assert announcements[0]["content_id"] == digest
            assert announcements[0]["source_peer_id"] == "update-source"

            with urllib.request.urlopen(peer_b.http_base_url + f"/updates/content/{digest}", timeout=5) as response:
                assert response.read() == artifact
            assert (export_b / "p2p" / digest).read_bytes() == artifact
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_node_seeds_local_update_manifest_on_startup(tmp_path: Path, monkeypatch) -> None:
    export_dir = tmp_path / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "channel": "dev",
        "version": "0.3.0",
        "sha256": "a" * 64,
        "content_id": "a" * 64,
        "url": "http://lan-peer/release.tar.gz",
        "size_bytes": 1024,
        "signature": "mock_sig_123",
    }
    (export_dir / "update.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    node = network_node.NetworkNode(_config(export_dir, "lan-node-a"))
    node.peer_network._seed_local_update_manifests()

    announcements = node.peer_network.update_announcements()
    assert len(announcements) == 1
    assert announcements[0]["version"] == "0.3.0"
    assert announcements[0]["content_id"] == "a" * 64
