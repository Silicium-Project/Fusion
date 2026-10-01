"""NAT traversal: STUN defaults, connectivity candidates and UDP hole punching.

Covers ``apply_nat_traversal_defaults``, local/server-observed candidate gathering
and validation (malformed, expired, duplicates, IPv4/IPv6 formatting) and the
native UDP hole-punch handshake (success, wrong session/peer, timeout, duplicate acks).
"""

import threading
import time
import types
from pathlib import Path

from tools import network_node, node_defaults
from tests.network_node_support import _config, _peer_registration_payload


def test_nat_punch_defaults_to_public_stun_for_ice() -> None:
    args = types.SimpleNamespace(
        nat_punch_enable=True,
        p2p_direct_transport_backend="auto",
        p2p_stun_server="",
    )

    resolved = network_node.apply_nat_traversal_defaults(args)

    assert resolved.p2p_stun_server == node_defaults.DEFAULT_PUBLIC_STUN_SERVER


def test_nat_punch_preserves_explicit_stun_and_native_backend() -> None:
    explicit = types.SimpleNamespace(
        nat_punch_enable=True,
        p2p_direct_transport_backend="ice",
        p2p_stun_server="stun.example.test:3478",
    )
    native = types.SimpleNamespace(
        nat_punch_enable=True,
        p2p_direct_transport_backend="native-light",
        p2p_stun_server="",
    )

    assert network_node.apply_nat_traversal_defaults(explicit).p2p_stun_server == "stun.example.test:3478"
    assert network_node.apply_nat_traversal_defaults(native).p2p_stun_server == ""


def _signed_punch_start(signal: network_node.PeerNetwork, peer_a: network_node.PeerNetwork, peer_b: network_node.PeerNetwork, session_id: str = "p2p-sess-test") -> dict:
    pairs = signal._candidate_pairs(_peer_registration_payload(peer_a), _peer_registration_payload(peer_b))
    session = {
        "session_id": session_id,
        "initiator_peer_id": peer_a.node_id,
        "target_peer_id": peer_b.node_id,
        "candidate_pairs": pairs,
    }
    return signal._punch_start_message(session)


def test_candidate_gathering_reports_host_and_server_observed_candidates(tmp_path: Path) -> None:
    config = _config(tmp_path / "peer", "node-a", p2p_candidate_ttl_s=30, p2p_candidate_refresh_s=1)
    config.gossip_port = 46101
    config.gossip_advertise_host = "192.168.1.20"
    peer = network_node.PeerNetwork(config, tmp_path / "peer")

    host_candidates = peer.refresh_candidates(force=True)
    host = next(candidate for candidate in host_candidates if candidate["ip"] == "192.168.1.20")
    assert host["candidate_type"] == "host"
    assert host["address_family"] == "ipv4"
    assert host["private"] is True
    assert host["internet_routable"] is False
    assert host["expires_unix"] > int(time.time())

    observed = peer.record_observed_candidate("93.184.216.34", source="observe:http://seed")
    assert observed is not None
    assert observed["candidate_type"] == "srflx"
    assert observed["internet_routable"] is True
    diagnostics = peer.candidate_diagnostics()
    assert diagnostics["observed_public_address"] == "93.184.216.34"
    assert diagnostics["selected_candidate"]["candidate_type"] == "srflx"
    assert (tmp_path / "peer" / "p2p.candidates.json").exists()


def test_candidate_validation_rejects_malformed_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "host", "transport": "udp", "ip": "not-an-ip", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "tcp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "invalid", "transport": "udp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "udp", "ip": "127.0.0.1", "port": 0, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    assert candidates == []


def test_candidate_validation_rejects_expired_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [{"candidate_type": "host", "transport": "udp", "ip": "127.0.0.1", "port": 46101, "observed_unix": now - 60, "expires_unix": now - 1}],
        "node-b",
        now,
    )

    assert candidates == []


def test_candidate_validation_deduplicates_candidates(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "host", "transport": "udp", "ip": "10.0.0.5", "port": 46101, "priority": 10, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "host", "transport": "udp", "ip": "10.0.0.5", "port": 46101, "priority": 30, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    assert len(candidates) == 1
    assert candidates[0]["priority"] == 30


def test_candidate_validation_formats_ipv4_and_ipv6(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    now = int(time.time())

    candidates = peer._normalize_candidate_list(
        [
            {"candidate_type": "srflx", "transport": "udp", "ip": "93.184.216.34", "port": 46101, "observed_unix": now, "expires_unix": now + 30},
            {"candidate_type": "srflx", "transport": "udp", "ip": "[2001:4860:4860::8888]", "port": 46102, "observed_unix": now, "expires_unix": now + 30},
        ],
        "node-b",
        now,
    )

    by_ip = {candidate["ip"]: candidate for candidate in candidates}
    assert by_ip["2001:4860:4860::8888"]["address_family"] == "ipv6"
    assert by_ip["93.184.216.34"]["address_family"] == "ipv4"


def test_udp_hole_punch_establishes_direct_session_between_local_nodes(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_a.gossip_advertise_host = "127.0.0.1"
    config_b.gossip_advertise_host = "127.0.0.1"
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b)
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=3)
        thread_b.join(timeout=3)

        assert results["a"]["status"] == "direct"
        assert results["b"]["status"] == "direct"
        assert results["a"]["transport_backend"] == "native-light"
        assert results["b"]["transport_backend"] == "native-light"
        assert results["a"]["rtt_ms"] >= 0
        assert results["a"]["selected_candidate_pair"]["local_candidate_id"]
        assert (tmp_path / "peer-a" / "p2p.direct_sessions.json").exists()
    finally:
        peer_b.stop()
        peer_a.stop()


def test_udp_hole_punch_rejects_wrong_session_id(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_retry_count=2, p2p_punch_interval_ms=10, p2p_session_timeout_ms=120)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True)
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b, session_id="p2p-sess-a")
        wrong_probe = {
            "message_type": "punch_probe",
            "session_id": "p2p-sess-wrong",
            "peer_id": "node-b",
            "target_peer_id": "node-a",
            "candidate_id": "cand-b",
            "nonce": "probe-wrong",
            "timestamp_unix": int(time.time()),
        }
        peer_b._sign_message(wrong_probe)
        peer_a._handle_network_message(wrong_probe, f"127.0.0.1:{config_b.gossip_port}")
        assert all(
            item.get("session_id") != "p2p-sess-wrong"
            for item in peer_a.direct_sessions_snapshot().get("sessions", [])
        )

        result = peer_a.establish_direct_udp_session(punch_start)
        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
    finally:
        peer_b.stop()
        peer_a.stop()


def test_udp_hole_punch_rejects_wrong_peer_id(tmp_path: Path) -> None:
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "peer-a", "node-a", gossip_enable=False, nat_punch_enable=True),
        tmp_path / "peer-a",
    )
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    punch_start = {
        "message_type": "punch_start",
        "session_id": "p2p-sess-wrong-peer",
        "peer_id": "node-signal",
        "identity_id": signal.identity.identity_id,
        "public_key": signal.identity.public_key_b64,
        "initiator_peer_id": "node-x",
        "target_peer_id": "node-y",
        "candidate_pairs": [],
        "timestamp_unix": int(time.time()),
        "nonce": "punch-start-wrong-peer",
    }
    signal._sign_message(punch_start)

    result = peer_a.establish_direct_udp_session(punch_start)
    assert result["status"] == "failed"
    assert result["failure_reason"] == "wrong_peer_id"


def test_udp_hole_punch_times_out_with_unreachable_candidate(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_retry_count=2, p2p_punch_interval_ms=10, p2p_session_timeout_ms=120)
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    try:
        now = int(time.time())
        local = next(candidate for candidate in peer_a.refresh_candidates(force=True) if candidate["address_family"] == "ipv4")
        remote = {
            "candidate_id": "cand-node-b-unreachable",
            "peer_id": "node-b",
            "address_family": "ipv4",
            "transport": "udp",
            "ip": "127.0.0.1",
            "port": 9,
            "candidate_type": "host",
            "priority": 100,
            "observed_unix": now,
            "expires_unix": now + 30,
            "source": "test",
        }
        punch_start = signal._punch_start_message(
            {
                "session_id": "p2p-sess-timeout",
                "initiator_peer_id": "node-a",
                "target_peer_id": "node-b",
                "candidate_pairs": [
                    {
                        "local_candidate_id": local["candidate_id"],
                        "remote_candidate_id": remote["candidate_id"],
                        "transport": "udp",
                        "address_family": "ipv4",
                        "priority": 100,
                        "local_candidate": local,
                        "remote_candidate": remote,
                    }
                ],
            }
        )

        result = peer_a.establish_direct_udp_session(punch_start)
        assert result["status"] == "failed"
        assert result["failure_reason"] == "timeout"
    finally:
        peer_a.stop()


def test_udp_hole_punch_ignores_duplicate_acks(tmp_path: Path) -> None:
    config_a = _config(tmp_path / "peer-a", "node-a", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_b = _config(tmp_path / "peer-b", "node-b", gossip_enable=True, nat_punch_enable=True, p2p_punch_interval_ms=10, p2p_session_timeout_ms=2500)
    config_a.gossip_advertise_host = "127.0.0.1"
    config_b.gossip_advertise_host = "127.0.0.1"
    peer_a = network_node.PeerNetwork(config_a, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(config_b, tmp_path / "peer-b")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a.start()
    peer_b.start()
    try:
        punch_start = _signed_punch_start(signal, peer_a, peer_b, session_id="p2p-sess-dup")
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=3)
        thread_b.join(timeout=3)
        assert results["a"]["status"] == "direct"

        session = peer_a._direct_sessions["p2p-sess-dup"]
        sent_probe_nonce = next(iter(session["sent_probes"].keys()))
        ack = {
            "message_type": "punch_ack",
            "session_id": "p2p-sess-dup",
            "peer_id": "node-b",
            "target_peer_id": "node-a",
            "probe_nonce": sent_probe_nonce,
            "selected_remote_candidate_id": session["selected_candidate_pair"]["local_candidate_id"],
            "selected_local_candidate_id": session["selected_candidate_pair"]["remote_candidate_id"],
            "nonce": session["seen_ack_nonces"][0],
            "timestamp_unix": int(time.time()),
        }
        peer_b._sign_message(ack)
        before = list(peer_a._direct_sessions["p2p-sess-dup"]["seen_ack_nonces"])
        peer_a._handle_network_message(ack, f"127.0.0.1:{config_b.gossip_port}")
        after = list(peer_a._direct_sessions["p2p-sess-dup"]["seen_ack_nonces"])
        assert after == before
    finally:
        peer_b.stop()
        peer_a.stop()
