"""Direct transport backends and ICE sessions.

Covers backend selection (unknown backend, ``auto`` -> ICE, missing optional
dependency), the ICE backend against a fake ``aioice`` contract and a real loopback session,
and the ICE data plane (content fetch, seed as rendezvous for private peers).
"""

import importlib.util
import json
import threading
import time
import types
from pathlib import Path

import pytest

from tools import direct_transport, network_node
from tests.network_node_support import _config, _peer_registration_payload


class _FakeIceCandidate:
    def __init__(
        self,
        foundation: str = "fake-foundation",
        component: int = 1,
        transport: str = "udp",
        priority: int = 2130706431,
        host: str = "127.0.0.1",
        port: int = 49000,
        type: str = "host",
        **_kwargs: object,
    ) -> None:
        self.foundation = foundation
        self.component = component
        self.transport = transport
        self.priority = priority
        self.host = host
        self.port = port
        self.type = type

    @classmethod
    def from_sdp(cls, sdp: str) -> "_FakeIceCandidate":
        parts = str(sdp).split()
        candidate_type = parts[7] if len(parts) > 7 and parts[6] == "typ" else "host"
        return cls(
            foundation=parts[0] if len(parts) > 0 else "remote-foundation",
            component=int(parts[1]) if len(parts) > 1 else 1,
            transport=parts[2] if len(parts) > 2 else "udp",
            priority=int(parts[3]) if len(parts) > 3 else 1,
            host=parts[4] if len(parts) > 4 else "127.0.0.1",
            port=int(parts[5]) if len(parts) > 5 else 49000,
            type=candidate_type,
        )

    def to_sdp(self) -> str:
        return f"{self.foundation} {self.component} {self.transport} {self.priority} {self.host} {self.port} typ {self.type}"


class _FakeIceConnection:
    _next_port = 49000

    def __init__(self, ice_controlling: bool, **_kwargs: object) -> None:
        _FakeIceConnection._next_port += 1
        self.ice_controlling = ice_controlling
        self.local_username = "ufrag-controlling" if ice_controlling else "ufrag-controlled"
        self.local_password = "pwd-controlling" if ice_controlling else "pwd-controlled"
        self.local_candidates: list[_FakeIceCandidate] = []
        self.remote_candidates: list[_FakeIceCandidate | None] = []
        self.remote_username = ""
        self.remote_password = ""
        self._candidate = _FakeIceCandidate(port=_FakeIceConnection._next_port)

    async def gather_candidates(self) -> None:
        self.local_candidates = [self._candidate]

    def get_default_candidate(self, _component: int) -> _FakeIceCandidate:
        return self._candidate

    async def add_remote_candidate(self, candidate: _FakeIceCandidate | None) -> None:
        self.remote_candidates.append(candidate)

    async def connect(self) -> None:
        if not self.remote_username or not self.remote_password:
            raise ConnectionError("remote credentials missing")


def _fake_aioice_module() -> types.SimpleNamespace:
    return types.SimpleNamespace(Connection=_FakeIceConnection, Candidate=_FakeIceCandidate)


def test_direct_transport_backend_rejects_unknown_backend(tmp_path: Path) -> None:
    config = _config(
        tmp_path / "peer",
        "node-a",
        gossip_enable=False,
        p2p_direct_transport_backend="custom-ice",
    )

    try:
        network_node.PeerNetwork(config, tmp_path / "peer")
        raise AssertionError("expected unsupported direct transport backend")
    except ValueError as exc:
        assert str(exc) == "unsupported_direct_transport_backend:custom-ice"


def test_direct_transport_auto_selects_ice_when_dependency_is_available(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object() if name == "aioice" else None)
    peer = network_node.PeerNetwork(
        _config(tmp_path / "auto-ice", "node-auto", gossip_enable=False, p2p_direct_transport_backend="auto"),
        tmp_path / "auto-ice",
    )
    assert peer.direct_transport.name == "ice"


def test_ice_direct_transport_builds_ready_payload_and_features(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    config = _config(
        tmp_path / "peer",
        "node-a",
        gossip_enable=False,
        nat_punch_enable=True,
        p2p_direct_transport_backend="ice",
        p2p_stun_server="stun.example.test:3478",
        p2p_turn_server="turn.example.test:3478",
        p2p_turn_username="turn-user",
        p2p_turn_password="turn-pass",
        p2p_turn_transport="tcp",
    )
    peer = network_node.PeerNetwork(config, tmp_path / "peer")

    diagnostics = peer.candidate_diagnostics()
    ready = peer.build_session_ready_payload({"session_id": "ice-sess", "initiator_peer_id": "node-a", "target_peer_id": "node-b"})

    assert peer.direct_transport.name == "ice"
    assert "ice_v1" in diagnostics["direct_transport_features"]
    assert "stun_v1" in diagnostics["direct_transport_features"]
    assert "turn_v1" in diagnostics["direct_transport_features"]
    assert ready["direct_transport_backend"] == "ice"
    assert ready["ice"]["supported"] is True
    assert ready["ice"]["ufrag"] == "ufrag-controlling"
    assert ready["ice"]["candidates"][0]["ice_sdp"]
    assert ready["ice"]["turn_server"] == "turn.example.test:3478"
    assert "turn-pass" not in json.dumps(ready)


def test_ice_signaling_embeds_ready_candidates_in_punch_start(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    signal_export = tmp_path / "signal"
    peer_a_export = tmp_path / "ice-a"
    peer_b_export = tmp_path / "ice-b"
    signal = network_node.PeerNetwork(_config(signal_export, "node-signal", gossip_enable=False), signal_export)
    peer_a = network_node.PeerNetwork(
        _config(peer_a_export, "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        peer_a_export,
    )
    peer_b = network_node.PeerNetwork(
        _config(peer_b_export, "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        peer_b_export,
    )

    signal._record_peer(_peer_registration_payload(peer_a))
    signal._record_peer(_peer_registration_payload(peer_b))
    status, body = signal.create_signaling_session(
        {"peer_id": "node-a", "target_peer_id": "node-b", "purpose": "nat_punch", "allowed_transports": ["ice"]},
        "node-a",
    )
    assert status == 201
    session = body["session"]
    ready_a = peer_a.build_session_ready_payload(session)
    ready_b = peer_b.build_session_ready_payload(session)

    first_status, first_body = signal.mark_session_ready(session["session_id"], "node-a", ready_a)
    second_status, second_body = signal.mark_session_ready(session["session_id"], "node-b", ready_b)

    assert first_status == 200
    assert first_body["session"]["status"] == "ready_wait"
    assert second_status == 200
    assert second_body["session"]["status"] == "punching"
    punch_start = second_body["punch_start"]
    assert punch_start["ice"]["peers"]["node-a"]["candidates"][0]["ice_sdp"]
    assert punch_start["ice"]["peers"]["node-b"]["ufrag"] == "ufrag-controlled"


def test_ice_backend_establishes_session_through_aioice_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(direct_transport.importlib, "import_module", lambda name: _fake_aioice_module() if name == "aioice" else None)
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "ice-a", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-a",
    )
    peer_b = network_node.PeerNetwork(
        _config(tmp_path / "ice-b", "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-b",
    )
    session = {
        "session_id": "ice-sess-direct",
        "initiator_peer_id": "node-a",
        "target_peer_id": "node-b",
        "candidate_pairs": [],
    }
    ready_a = peer_a.build_session_ready_payload(session)
    ready_b = peer_b.build_session_ready_payload(session)
    punch_start = signal._punch_start_message({**session, "ready_transports": {"node-a": ready_a, "node-b": ready_b}})

    result_a = peer_a.establish_direct_udp_session(punch_start)
    result_b = peer_b.establish_direct_udp_session(punch_start)

    assert result_a["status"] == "direct"
    assert result_b["status"] == "direct"
    assert result_a["transport_backend"] == "ice"
    assert result_b["transport_backend"] == "ice"
    assert result_a["selected_candidate_pair"]["remote_candidate_id"]
    assert (tmp_path / "ice-a" / "p2p.direct_sessions.json").exists()
    deadline = time.time() + 5
    while not peer_a.recent_transport_attestations(1) and time.time() < deadline:
        time.sleep(0.05)
    attestation = peer_a.recent_transport_attestations(1)[0]
    assert attestation["route"] == "direct"
    assert attestation["proof_scope"] == "connectivity_check"
    assert network_node.PeerNetwork.verify_transport_attestation(attestation)


def test_ice_backend_establishes_real_loopback_session_when_installed(tmp_path: Path) -> None:
    pytest.importorskip("aioice")
    signal = network_node.PeerNetwork(_config(tmp_path / "signal", "node-signal", gossip_enable=False), tmp_path / "signal")
    peer_a = network_node.PeerNetwork(
        _config(tmp_path / "real-ice-a", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "real-ice-a",
    )
    peer_b = network_node.PeerNetwork(
        _config(tmp_path / "real-ice-b", "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "real-ice-b",
    )
    session = {
        "session_id": "real-ice-loopback",
        "initiator_peer_id": "node-a",
        "target_peer_id": "node-b",
        "candidate_pairs": [],
    }
    try:
        ready_a = peer_a.build_session_ready_payload(session)
        ready_b = peer_b.build_session_ready_payload(session)
        punch_start = signal._punch_start_message({**session, "ready_transports": {"node-a": ready_a, "node-b": ready_b}})
        results: dict[str, dict] = {}
        thread_a = threading.Thread(target=lambda: results.setdefault("a", peer_a.establish_direct_udp_session(punch_start)))
        thread_b = threading.Thread(target=lambda: results.setdefault("b", peer_b.establish_direct_udp_session(punch_start)))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)
        assert results["a"]["status"] == "direct"
        assert results["b"]["status"] == "direct"
        assert results["a"]["transport_backend"] == "ice"
        assert results["b"]["transport_backend"] == "ice"
    finally:
        peer_a.direct_transport.close()
        peer_b.direct_transport.close()


def test_ice_data_plane_fetches_content_without_http_payload(tmp_path: Path) -> None:
    pytest.importorskip("aioice")
    export_a = tmp_path / "data-a"
    export_b = tmp_path / "data-b"
    peer_a = network_node.PeerNetwork(
        _config(export_a, "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        export_a,
    )
    peer_b = network_node.PeerNetwork(
        _config(export_b, "node-b", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        export_b,
    )
    peer_a.start()
    peer_b.start()
    try:
        peer_a._record_peer(_peer_registration_payload(peer_b))
        peer_b._record_peer(_peer_registration_payload(peer_a))
        expected_data = b"ice-data-plane-" * 5000
        stored = network_node.P2PClient(peer_b.config.p2p_gateway, export_b, peer_b).put_local(expected_data)
        peer_a._fetch_direct_from_peer = lambda _peer, _content_id: None
        result = network_node.P2PClient(peer_a.config.p2p_gateway, export_a, peer_a).fetch(stored["shared_ref"])
        assert result[0] == expected_data
        assert result[1]["source"] == "silicium-ice"
        assert result[1]["transport_backend"] == "ice"
        assert result[1]["transport_route"] == "direct"
        assert result[1]["path_attestation"]["proof_scope"] == "payload_transfer"
        assert result[1]["path_attestation"]["peer_proof_verified"] is True
        assert network_node.PeerNetwork.verify_transport_attestation(result[1]["path_attestation"])
    finally:
        peer_a.stop()
        peer_b.stop()


def test_ice_data_plane_uses_seed_as_rendezvous_for_private_peers(tmp_path: Path) -> None:
    pytest.importorskip("aioice")
    signal_export = tmp_path / "signal"
    export_a = tmp_path / "rendezvous-a"
    export_b = tmp_path / "rendezvous-b"
    signal = network_node.PeerNetwork(_config(signal_export, "signal", gossip_enable=False), signal_export)
    signal.start()
    peer_a = network_node.PeerNetwork(
        _config(
            export_a,
            "node-a",
            gossip_enable=False,
            nat_punch_enable=True,
            p2p_direct_transport_backend="ice",
            seed_peers=[signal.http_base_url],
        ),
        export_a,
    )
    peer_b = network_node.PeerNetwork(
        _config(
            export_b,
            "node-b",
            gossip_enable=False,
            nat_punch_enable=True,
            p2p_direct_transport_backend="ice",
            seed_peers=[signal.http_base_url],
        ),
        export_b,
    )
    peer_a.start()
    peer_b.start()
    stop_poll = threading.Event()

    def poll_target_signaling() -> None:
        while not stop_poll.wait(0.05):
            peer_b._poll_signaling_sessions(signal.http_base_url)

    poll_thread = threading.Thread(target=poll_target_signaling, daemon=True)
    try:
        signal._record_peer(_peer_registration_payload(peer_a))
        signal._record_peer(_peer_registration_payload(peer_b))
        peer_a._record_peer(_peer_registration_payload(peer_b))
        peer_b._record_peer(_peer_registration_payload(peer_a))
        expected_data = b"rendezvous-ice-data-plane-" * 3000
        stored = network_node.P2PClient(peer_b.config.p2p_gateway, export_b, peer_b).put_local(expected_data)
        peer_a._fetch_direct_from_peer = lambda _peer, _content_id: None
        poll_thread.start()

        result = network_node.P2PClient(peer_a.config.p2p_gateway, export_a, peer_a).fetch(stored["shared_ref"])

        assert result[0] == expected_data
        assert result[1]["source"] == "silicium-ice"
        assert result[1]["transport_backend"] == "ice"
        deadline = time.time() + 2
        while time.time() < deadline and signal.sessions_snapshot()["sessions"][0]["status"] != "direct":
            time.sleep(0.05)
        assert signal.sessions_snapshot()["sessions"][0]["status"] == "direct"
    finally:
        stop_poll.set()
        poll_thread.join(timeout=2)
        peer_a.stop()
        peer_b.stop()
        signal.stop()


def test_ice_backend_reports_missing_optional_dependency(tmp_path: Path, monkeypatch) -> None:
    def _missing_aioice(name: str) -> object:
        if name == "aioice":
            raise ModuleNotFoundError("aioice")
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(direct_transport.importlib, "import_module", _missing_aioice)
    peer = network_node.PeerNetwork(
        _config(tmp_path / "ice-missing", "node-a", gossip_enable=False, nat_punch_enable=True, p2p_direct_transport_backend="ice"),
        tmp_path / "ice-missing",
    )

    ready = peer.build_session_ready_payload({"session_id": "ice-sess", "initiator_peer_id": "node-a", "target_peer_id": "node-b"})

    assert ready["direct_transport_backend"] == "ice"
    assert ready["ice"]["supported"] is False
    assert ready["ice"]["error"] == "aioice_missing"
