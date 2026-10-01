"""Peer discovery, gossip, HTTP peer sync, relay, replication and routing.

Covers UDP gossip broadcast robustness and fan-out bounds, peer sync over HTTP
with public identities, discovery through seed registries, server-observed
candidates, relay fetches for unreachable peers, storage replication quorum and
the Dijkstra route table.
"""

import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _config


def test_udp_route_failure_does_not_escape_gossip_broadcast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    peer = network_node.PeerNetwork(
        _config(tmp_path / "peer", "node-a", gossip_enable=False),
        tmp_path / "peer",
    )

    class UnreachableSocket:
        def sendto(self, _payload: bytes, _target: tuple[str, int]) -> None:
            raise OSError(10051, "network unreachable")

        def close(self) -> None:
            return None

    monkeypatch.setattr(socket, "socket", lambda *_args, **_kwargs: UnreachableSocket())
    peer._udp_socket = None
    peer._send_udp("192.0.2.1:46102", "192.0.2.1", 46102, {"message_type": "gossip_event"})


def test_peer_network_gossips_and_serves_p2p_content(tmp_path: Path) -> None:
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

            stored = p2p_a.put_local(b"hello-peers")
            shared_ref = stored["shared_ref"]
            data, meta = p2p_b.fetch(shared_ref)
            assert data == b"hello-peers"
            assert meta["source"] == "silicium-peer"
            assert meta["peer_id"] == "node-a"

            peer_a.publish("fragment_result", {"result_hash": "sha256:test", "proof_ref": shared_ref})
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if (export_b / "gossip.events.ndjson").exists():
                    lines = (export_b / "gossip.events.ndjson").read_text(encoding="utf-8").splitlines()
                    if any('"topic":"fragment_result"' in line for line in lines):
                        break
                time.sleep(0.05)
            assert (export_b / "gossip.events.ndjson").exists()
            assert '"topic":"fragment_result"' in (export_b / "gossip.events.ndjson").read_text(encoding="utf-8")
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_peer_network_syncs_over_http_with_public_identity(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        unauthorized = urllib.request.Request(peer_a.http_base_url + "/peers")
        try:
            urllib.request.urlopen(unauthorized, timeout=2)
            raise AssertionError("expected mesh auth failure")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403

        config_b = _config(
            export_b,
            "node-b",
            gossip_enable=False,
            seed_peers=[peer_a.http_base_url],
            peer_sync_interval_s=1,
        )
        peer_b = network_node.PeerNetwork(config_b, export_b)
        p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
        peer_b.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_b.sync_once()
                if peer_b.peers_snapshot()["count"] >= 2 and peer_a.peers_snapshot()["count"] >= 2:
                    break
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 2
            assert peer_a.peers_snapshot()["count"] >= 2

            stored = p2p_a.put_local(b"hello-http-mesh")
            data, meta = p2p_b.fetch(stored["shared_ref"])
            assert data == b"hello-http-mesh"
            assert meta["source"] == "silicium-peer"

            peer_a.publish("fragment_result", {"result_hash": "sha256:http", "proof_ref": stored["shared_ref"]})
            deadline = time.time() + 3.0
            while time.time() < deadline:
                if (export_b / "gossip.events.ndjson").exists():
                    lines = (export_b / "gossip.events.ndjson").read_text(encoding="utf-8").splitlines()
                    if any('"topic":"fragment_result"' in line for line in lines):
                        break
                time.sleep(0.05)
            assert (export_b / "gossip.events.ndjson").exists()
            assert '"topic":"fragment_result"' in (export_b / "gossip.events.ndjson").read_text(encoding="utf-8")
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_peer_network_discovers_server_observed_candidate_over_http(tmp_path: Path) -> None:
    export_a = tmp_path / "a"
    export_b = tmp_path / "b"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    peer_a.start()
    try:
        config_b = _config(
            export_b,
            "node-b",
            gossip_enable=False,
            seed_peers=[peer_a.http_base_url],
            p2p_candidate_ttl_s=30,
            p2p_candidate_refresh_s=1,
        )
        config_b.gossip_port = 46102
        peer_b = network_node.PeerNetwork(config_b, export_b)
        peer_b.start()
        try:
            candidates = peer_b.refresh_candidates(force=True)
            observed = [candidate for candidate in candidates if candidate["candidate_type"] == "srflx"]
            assert observed
            assert observed[0]["source"].startswith("observe:")
            assert observed[0]["ip"] == "127.0.0.1"
        finally:
            peer_b.stop()
    finally:
        peer_a.stop()


def test_peer_network_relay_fetches_unreachable_peer_content(tmp_path: Path) -> None:
    export_a = tmp_path / "relay-a"
    export_b = tmp_path / "relay-b"
    export_c = tmp_path / "relay-c"
    config_a = _config(export_a, "node-a", gossip_enable=False)
    peer_a = network_node.PeerNetwork(config_a, export_a)
    p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
    peer_a.start()
    try:
        config_c = _config(export_c, "node-c", gossip_enable=False, relay_enable=True, seed_peers=[peer_a.http_base_url], peer_sync_interval_s=1)
        peer_c = network_node.PeerNetwork(config_c, export_c)
        peer_c.start()
        try:
            config_b = _config(export_b, "node-b", gossip_enable=False, relay_enable=True, seed_peers=[peer_c.http_base_url], peer_sync_interval_s=1)
            peer_b = network_node.PeerNetwork(config_b, export_b)
            p2p_b = network_node.P2PClient(config_b.p2p_gateway, export_b, peer_b)
            peer_b.start()
            try:
                deadline = time.time() + 8.0
                while time.time() < deadline:
                    peer_b.sync_once()
                    peer_c.sync_once()
                    if peer_b.peers_snapshot()["count"] >= 3:
                        break
                    time.sleep(0.05)
                assert peer_b.peers_snapshot()["count"] >= 3

                stored = p2p_a.put_local(b"relay-path")
                content_id = str(stored["shared_ref"]["content_id"])
                deadline = time.time() + 8.0
                while time.time() < deadline:
                    target_peer = peer_c._peers.get("node-a", {})
                    if peer_c._fetch_direct_from_peer(target_peer, content_id) == b"relay-path":
                        break
                    peer_c.sync_once()
                    time.sleep(0.05)
                peer_b._peers["node-a"]["http_base_url"] = "http://127.0.0.1:9"
                data, meta = p2p_b.fetch(stored["shared_ref"])
                assert data == b"relay-path"
                assert meta["relayed_via"] == "node-c"
                assert meta["transport_route"] == "relay"
                assert meta["path_attestation"]["route"] == "relay"
                assert network_node.PeerNetwork.verify_transport_attestation(meta["path_attestation"])
            finally:
                peer_b.stop()
        finally:
            peer_c.stop()
    finally:
        peer_a.stop()


def test_storage_replication_meets_quorum(tmp_path: Path) -> None:
    export_a = tmp_path / "replica-a"
    export_b = tmp_path / "replica-b"
    export_c = tmp_path / "replica-c"
    config_b = _config(export_b, "node-b", gossip_enable=False, roles="storage", reputation_score=2.0)
    config_c = _config(export_c, "node-c", gossip_enable=False, roles="storage", reputation_score=1.0)
    peer_b = network_node.PeerNetwork(config_b, export_b)
    peer_c = network_node.PeerNetwork(config_c, export_c)
    peer_b.start()
    peer_c.start()
    try:
        config_a = _config(
            export_a,
            "node-a",
            gossip_enable=False,
            roles="storage",
            seed_peers=[peer_b.http_base_url, peer_c.http_base_url],
            peer_sync_interval_s=1,
            replication_factor=2,
            replication_quorum=2,
        )
        peer_a = network_node.PeerNetwork(config_a, export_a)
        p2p_a = network_node.P2PClient(config_a.p2p_gateway, export_a, peer_a)
        peer_a.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_a.sync_once()
                if peer_a.peers_snapshot()["count"] >= 3:
                    break
                time.sleep(0.05)
            stored = p2p_a.put_local(b"replicated-bytes", replication_factor=2, replication_quorum=2, replication_roles={"storage"})
            digest = stored["shared_ref"]["content_id"]
            assert stored["replication"]["satisfied"] is True
            assert stored["replication"]["stored"] == 2
            assert (export_b / "p2p" / digest).exists()
            assert (export_c / "p2p" / digest).exists()
        finally:
            peer_a.stop()
    finally:
        peer_b.stop()
        peer_c.stop()


def test_peer_network_discovers_peers_via_public_seed_registry(tmp_path: Path) -> None:
    export_seed = tmp_path / "seed"
    export_b = tmp_path / "discover-b"
    export_c = tmp_path / "discover-c"
    seed = network_node.PeerNetwork(_config(export_seed, "seed-node", gossip_enable=False), export_seed)
    seed.start()
    try:
        peer_b = network_node.PeerNetwork(
            _config(export_b, "node-b", gossip_enable=False, discovery_seeds=[seed.http_base_url], peer_sync_interval_s=1),
            export_b,
        )
        peer_c = network_node.PeerNetwork(
            _config(export_c, "node-c", gossip_enable=False, discovery_seeds=[seed.http_base_url], peer_sync_interval_s=1),
            export_c,
        )
        peer_b.start()
        peer_c.start()
        try:
            deadline = time.time() + 3.0
            while time.time() < deadline:
                peer_b.sync_once()
                peer_c.sync_once()
                if peer_b.peers_snapshot()["count"] >= 3 and peer_c.peers_snapshot()["count"] >= 3:
                    break
                time.sleep(0.05)
            assert peer_b.peers_snapshot()["count"] >= 3
            assert peer_c.peers_snapshot()["count"] >= 3
        finally:
            peer_b.stop()
            peer_c.stop()
    finally:
        seed.stop()


def test_peer_network_uses_http_seed_peer_as_discovery_registry(tmp_path: Path) -> None:
    export_seed = tmp_path / "seed"
    export_peer = tmp_path / "peer"
    seed = network_node.PeerNetwork(_config(export_seed, "seed-node", gossip_enable=False), export_seed)
    seed.start()
    try:
        peer = network_node.PeerNetwork(
            _config(
                export_peer,
                "desktop-node",
                gossip_enable=False,
                seed_peers=[seed.http_base_url],
                p2p_direct_transport_backend="native-light",
            ),
            export_peer,
        )
        peer.start()
        try:
            peer.sync_once()
            registered = {item["node_id"]: item for item in seed.peers_snapshot()["peers"]}
            assert "desktop-node" in registered
            assert "direct_transport:native-light" in registered["desktop-node"]["features"]
        finally:
            peer.stop()
    finally:
        seed.stop()


def test_route_table_prefers_direct_path_with_dijkstra(tmp_path: Path) -> None:
    node = network_node.NetworkNode(_config(tmp_path / "routes", "node-a", roles="storage"))
    node.peer_network._peers.update(
        {
            "node-b": {
                "node_id": "node-b",
                "http_base_url": "http://node-b",
                "transport_attestations": [
                    {"remote_peer_id": "node-c", "route": "direct", "success": True}
                ],
            },
            "node-c": {"node_id": "node-c"},
        }
    )
    routes = {item["target_peer_id"]: item for item in node.peer_network.route_table_snapshot()}
    assert routes["node-b"]["transport"] == "central"
    assert routes["node-c"]["path"] == ["node-a", "node-b", "node-c"]
    assert routes["node-c"]["cost"] == 9.0


def test_peer_sync_fanout_keeps_seed_and_bounds_transitive_targets(tmp_path: Path) -> None:
    node = network_node.PeerNetwork(_config(tmp_path / "fanout", "node-a", gossip_enable=False, seed_peers=["http://seed:46001"]), tmp_path / "fanout")
    node.config.peer_sync_fanout = 2
    node.advertised_http_base_url = "http://node-a:46001"
    node._peers.update(
        {
            "peer-1": {"node_id": "peer-1", "http_base_url": "http://peer-1:46001"},
            "peer-2": {"node_id": "peer-2", "http_base_url": "http://peer-2:46001"},
            "peer-3": {"node_id": "peer-3", "http_base_url": "http://peer-3:46001"},
        }
    )

    assert node._sync_targets() == [
        "http://peer-1:46001",
        "http://peer-2:46001",
        "http://seed:46001",
    ]


def test_gossip_broadcast_bounds_peer_fanout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    node = network_node.PeerNetwork(
        _config(tmp_path / "gossip-fanout", "node-a", gossip_enable=False),
        tmp_path / "gossip-fanout",
    )
    node.config.peer_sync_fanout = 2
    node.advertised_http_base_url = "http://node-a:46001"
    node._peers.update(
        {
            f"peer-{index}": {"node_id": f"peer-{index}", "http_base_url": f"http://peer-{index}:46001"}
            for index in range(6)
        }
    )
    targets: list[str] = []
    monkeypatch.setattr(node, "_send_http", lambda base_url, _message: targets.append(base_url))

    node._broadcast({"message_type": "gossip_event", "event_id": "event-1"})

    assert len(targets) == 2
    assert set(targets).issubset({f"http://peer-{index}:46001" for index in range(6)})
