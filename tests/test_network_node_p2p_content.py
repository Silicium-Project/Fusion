"""P2P content fetching through ``P2PClient``.

Covers the verified local content cache, trying a public ICE peer before the
HTTP fallback, and falling back to the shared reference when the file path is
missing.
"""

import time
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _config


def test_p2p_client_uses_verified_local_silicium_cache(tmp_path: Path) -> None:
    export_dir = tmp_path / "cached-content"
    content = b"cached silicium payload"
    content_id = network_node.sha256_bytes(content)
    content_path = export_dir / "p2p" / content_id
    content_path.parent.mkdir(parents=True)
    content_path.write_bytes(content)

    class UnexpectedNetworkFetch:
        def fetch_content(self, *_args):
            raise AssertionError("network fetch should not run for verified local content")

    client = network_node.P2PClient("http://127.0.0.1:5001", export_dir, UnexpectedNetworkFetch())
    data, meta = client.fetch({"protocol": "silicium", "content_id": content_id})

    assert data == content
    assert meta["source"] == "local-silicium-cache"


def test_public_ice_peer_is_tried_before_http_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    export_dir = tmp_path / "public-http"
    peer = network_node.PeerNetwork(_config(export_dir, "worker-a", gossip_enable=False, nat_punch_enable=True), export_dir)
    public_peer = {
        "node_id": "orchestrator-1",
        "http_base_url": "https://orchestrator.example.test",
        "features": ["ice_v1"],
    }
    monkeypatch.setattr(peer, "peers_snapshot", lambda: {"peers": [public_peer]})
    events: list[str] = []
    monkeypatch.setattr(peer, "_fetch_direct_from_peer", lambda _peer, _content_id: (events.append("http"), b"public-content")[1])
    monkeypatch.setattr(
        peer,
        "_fetch_direct_ice",
        lambda *_args: (events.append("ice"), None)[1],
    )
    monkeypatch.setattr(
        peer,
        "_attested_fetch_meta",
        lambda selected, **_kwargs: {"node_id": selected["node_id"], "transport_backend": "peer-http"},
    )

    data, meta = peer.fetch_content("a" * 64, "orchestrator-1")

    assert data == b"public-content"
    assert meta["transport_backend"] == "peer-http"
    assert events == ["ice", "http"]


def test_p2p_fetch_falls_back_to_shared_ref_when_file_path_missing(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a")
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        config_b = _config(export_b, "node-b", seed_peers=[f"127.0.0.1:{config_a.gossip_port}"])
        peer_b = network_node.PeerNetwork(config_b, export_b)
        p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
        peer_b.start()
        try:
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if peer_b.peers_snapshot()["count"] >= 2:
                    break
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 2

            stored = p2p_a.put_local(b"verify-handoff-bytes")
            # Simulate a verify worker receiving the producer-local file ref: the
            # absolute path is foreign, but shared_ref remains resolvable.
            foreign_ref = {
                **stored,
                "content_id": str(tmp_path / "other-node" / "missing-export" / "p2p" / stored["shared_ref"]["content_id"]),
            }
            assert not Path(foreign_ref["content_id"]).exists()
            data, meta = p2p_b.fetch(foreign_ref)
            assert data == b"verify-handoff-bytes"
            assert meta["source"] == "silicium-peer"
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()
