"""P2P signaling sessions and signed transport-path attestations.

Covers signaling sessions brokered by a seed node over signed HTTP (authorised
sessions with candidate pairs, unauthorised pairings, expiry of stale sessions,
closing on peer disconnect) and the signed, persisted, tamper-evident transport
path attestations that peers publish and the registry verifies.
"""

import json
import time
from pathlib import Path

from tools import network_node
from tests.network_node_support import (
    _config,
    _peer_registration_payload,
    _signed_json_request_status,
    _signed_json_request,
)


def test_p2p_signaling_creates_authorized_session_with_candidate_pairs(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    peer_a_export = tmp_path / "peer-a"
    peer_b_export = tmp_path / "peer-b"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a_config = _config(peer_a_export, "node-a", gossip_enable=False)
    peer_b_config = _config(peer_b_export, "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46111
    peer_b_config.gossip_port = 46112
    peer_a = network_node.PeerNetwork(peer_a_config, peer_a_export)
    peer_b = network_node.PeerNetwork(peer_b_config, peer_b_export)
    task_dir = signal_export / "tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "compute_42.json").write_text(
        json.dumps({"task_id": "compute_42", "requester_peer_id": "node-a", "dispatched_to": "node-b"}),
        encoding="utf-8",
    )

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]

        status, body = _signed_json_request_status(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "task_id": "compute_42", "purpose": "fragment_fetch"},
        )
        assert status == 201
        session = body["session"]
        assert session["status"] == "signaling"
        assert session["initiator_peer_id"] == "node-a"
        assert session["target_peer_id"] == "node-b"
        assert session["candidate_pairs"]
        assert session["candidate_pairs"][0]["local_candidate"]["peer_id"] == "node-a"
        assert session["candidate_pairs"][0]["remote_candidate"]["peer_id"] == "node-b"

        session_id = session["session_id"]
        ready_a = _signed_json_request(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert ready_a["session"]["status"] == "ready_wait"
        ready_b = _signed_json_request(peer_b, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert ready_b["session"]["status"] == "punching"
        assert ready_b["punch_start"]["candidate_pairs"]
        path_attestation = peer_a.record_transport_attestation(
            route="direct",
            transport_backend="native-light",
            remote_peer_id="node-b",
            session_id=session_id,
            selected_candidate_pair=session["candidate_pairs"][0],
        )
        result = _signed_json_request(
            peer_a,
            signal.http_base_url,
            f"/p2p/sessions/{session_id}/result",
            {
                "ok": True,
                "transport": "direct",
                "selected_local_candidate_id": session["candidate_pairs"][0]["local_candidate_id"],
                "selected_remote_candidate_id": session["candidate_pairs"][0]["remote_candidate_id"],
                "path_attestation": path_attestation,
            },
        )
        assert result["session"]["status"] == "direct"
        assert result["session"]["results"][0]["ok"] is True
        assert result["session"]["results"][0]["attestation_verified"] is True
        assert (signal_export / "p2p.sessions.ndjson").exists()
    finally:
        signal.stop()


def test_p2p_signaling_rejects_unauthorized_pairing(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a = network_node.PeerNetwork(_config(tmp_path / "peer-a", "node-a", gossip_enable=False), tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(_config(tmp_path / "peer-b", "node-b", gossip_enable=False), tmp_path / "peer-b")
    task_dir = signal_export / "tasks"
    task_dir.mkdir(parents=True)
    (task_dir / "compute_42.json").write_text(
        json.dumps({"task_id": "compute_42", "requester_peer_id": "node-a", "dispatched_to": "node-c"}),
        encoding="utf-8",
    )

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        status, body = _signed_json_request_status(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "task_id": "compute_42", "purpose": "fragment_fetch"},
        )
        assert status == 403
        assert body["error"] == "task_peer_pair_unauthorized"
    finally:
        signal.stop()


def test_p2p_signaling_expires_stale_session(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False, p2p_session_ttl_s=1), signal_export)
    peer_a_config = _config(tmp_path / "peer-a", "node-a", gossip_enable=False)
    peer_b_config = _config(tmp_path / "peer-b", "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46121
    peer_b_config.gossip_port = 46122
    peer_a = network_node.PeerNetwork(peer_a_config, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(peer_b_config, tmp_path / "peer-b")

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        created = _signed_json_request(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch"},
        )
        session_id = created["session"]["session_id"]
        time.sleep(1.2)
        status, body = _signed_json_request_status(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert status == 404
        assert body["error"] == "session_not_found"
        assert signal.sessions_snapshot()["count"] == 0
    finally:
        signal.stop()


def test_p2p_signaling_closes_session_on_peer_disconnect(tmp_path: Path) -> None:
    signal_export = tmp_path / "signal"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a_config = _config(tmp_path / "peer-a", "node-a", gossip_enable=False)
    peer_b_config = _config(tmp_path / "peer-b", "node-b", gossip_enable=False)
    peer_a_config.gossip_port = 46131
    peer_b_config.gossip_port = 46132
    peer_a = network_node.PeerNetwork(peer_a_config, tmp_path / "peer-a")
    peer_b = network_node.PeerNetwork(peer_b_config, tmp_path / "peer-b")

    signal.start()
    try:
        assert _signed_json_request(peer_a, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_a))["ok"]
        assert _signed_json_request(peer_b, signal.http_base_url, "/p2p/peers/register", _peer_registration_payload(peer_b))["ok"]
        created = _signed_json_request(
            peer_a,
            signal.http_base_url,
            "/p2p/sessions/request",
            {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch"},
        )
        session_id = created["session"]["session_id"]
        closed = _signed_json_request(peer_b, signal.http_base_url, f"/p2p/sessions/{session_id}/close", {"reason": "peer_disconnect"})
        assert closed["session"]["status"] == "closed"
        status, body = _signed_json_request_status(peer_a, signal.http_base_url, f"/p2p/sessions/{session_id}/ready", {})
        assert status == 409
        assert body["error"] == "session_closed"
    finally:
        signal.stop()


def test_transport_path_attestation_is_signed_persisted_and_tamper_evident(tmp_path: Path) -> None:
    export_dir = tmp_path / "attested"
    peer = network_node.PeerNetwork(_config(export_dir, "node-a", gossip_enable=False), export_dir)

    attestation = peer.record_transport_attestation(
        route="direct",
        transport_backend="ice",
        remote_peer_id="node-b",
        session_id="p2p-sess-attested",
        proof_scope="payload_transfer",
        content_id="a" * 64,
        content_sha256="b" * 64,
        size_bytes=4096,
        selected_candidate_pair={
            "local_candidate_id": "candidate-a",
            "remote_candidate_id": "candidate-b",
        },
    )

    assert network_node.PeerNetwork.verify_transport_attestation(attestation)
    assert attestation["observer_peer_id"] == "node-a"
    assert attestation["route"] == "direct"
    assert attestation["signature"]
    assert (export_dir / "p2p.transport_attestations.json").exists()
    tampered = {**attestation, "route": "relay"}
    assert not network_node.PeerNetwork.verify_transport_attestation(tampered)

    reloaded = network_node.PeerNetwork(_config(export_dir, "node-a", gossip_enable=False), export_dir)
    reloaded._load_transport_attestations()
    assert reloaded.recent_transport_attestations(1)[0]["claim_hash"] == attestation["claim_hash"]


def test_peer_registry_accepts_only_verified_path_attestations(tmp_path: Path) -> None:
    peer_a = network_node.PeerNetwork(_config(tmp_path / "a", "node-a", gossip_enable=False), tmp_path / "a")
    peer_b = network_node.PeerNetwork(_config(tmp_path / "b", "node-b", gossip_enable=False), tmp_path / "b")
    attestation = peer_a.record_transport_attestation(
        route="direct",
        transport_backend="ice",
        remote_peer_id="node-b",
        session_id="p2p-sess-propagated",
    )
    payload = _peer_registration_payload(peer_a)

    peer_b._record_peer(payload)
    assert peer_b.peers_snapshot()["peers"][0]["transport_attestations"][0]["claim_hash"] == attestation["claim_hash"]

    tampered = {**attestation, "transport_backend": "fake-central-proxy"}
    peer_b._record_peer({**payload, "transport_attestations": [tampered]})
    stored = next(item for item in peer_b.peers_snapshot()["peers"] if item["node_id"] == "node-a")
    assert stored["transport_attestations"][0]["claim_hash"] == attestation["claim_hash"]
    assert stored["transport_attestations"][0]["transport_backend"] == "ice"
