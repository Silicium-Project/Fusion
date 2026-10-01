"""Node identity, session handshakes and signed peer authentication.

Covers ``NodeIdentity`` key persistence and in-process signing, signed session
handshake validation (replay, wrong peer, expiry, tampering, task authorisation),
mesh-key/dev bearer auth, reverse-proxy aware request signing, the ``/health``
endpoint and the CLI argument parser.
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from tools import network_node
from tests.network_node_support import _config


def test_network_node_parser_has_no_legacy_worker_binary() -> None:
    parser = network_node.build_arg_parser()

    args = parser.parse_args([])

    assert not hasattr(args, "worker_binary")


def _resign_handshake(peer: network_node.PeerNetwork, handshake: dict) -> dict:
    unsigned = dict(handshake)
    unsigned.pop("signature", None)
    unsigned["signature"] = peer.identity.sign_bytes(network_node.stable_json(unsigned).encode("utf-8"))
    return unsigned


class _RequestStub:
    def __init__(self, headers: dict[str, str], *, command: str = "GET", path: str = "/peers") -> None:
        self.headers = headers
        self.command = command
        self.path = path


def test_peer_identity_persists_across_restarts(tmp_path: Path) -> None:
    export_dir = tmp_path / "identity"
    config = _config(export_dir, "node-a")

    first = network_node.NodeIdentity(config)
    second = network_node.NodeIdentity(config)

    assert first.identity_id == second.identity_id
    assert first.public_key_b64 == second.public_key_b64
    assert first.private_key_path.exists()
    assert first.public_key_path.exists()


def test_peer_identity_signs_in_process_without_openssl_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("identity signing must not launch openssl.exe")

    monkeypatch.setattr(subprocess, "run", fail_subprocess)
    identity = network_node.NodeIdentity(_config(tmp_path / "identity-native", "node-native"))
    payload = b"signed without an external process"
    signature = identity.sign_bytes(payload)

    assert network_node.NodeIdentity.verify_bytes(payload, signature, identity.public_key_b64)
    assert not network_node.NodeIdentity.verify_bytes(payload + b"!", signature, identity.public_key_b64)


def test_seed_url_preserves_reverse_proxy_path(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a"), tmp_path / "peer")
    assert peer._normalize_http_target("https://vps.example/emitter/") == "https://vps.example/emitter"


def test_network_node_health_identifies_integrated_daemon(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "health", "node-health"), tmp_path / "health")
    peer.start()
    try:
        assert peer._http_server is not None
        assert peer._http_server.request_queue_size >= 64
        with urllib.request.urlopen(peer.http_base_url + "/healthz", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["ok"] is True
        assert payload["service"] == "network_node"
        assert payload["node_id"] == "node-health"
    finally:
        peer.stop()


def test_session_handshake_accepts_valid_signed_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a", roles="compute", reputation_score=25), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b", roles="verify"), tmp_path / "target")

    handshake = source.create_session_handshake(
        target_peer_id="node-b",
        session_id="sess-valid",
        purpose="fragment_fetch",
        task_id="task-1",
        candidate_fingerprints=[{"candidate_id": "cand-a", "expires_unix": int(time.time()) + 60}],
    )

    ok, reason = target.verify_session_handshake(
        handshake,
        expected_peer_id="node-a",
        expected_target_peer_id="node-b",
        authorized_task_ids={"task-1"},
    )
    assert ok, reason


def test_session_handshake_rejects_replay(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-replay")

    assert target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")[0]
    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_replay"


def test_session_handshake_rejects_wrong_peer_id(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-wrong-peer")

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-c", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_peer_mismatch"


def test_session_handshake_rejects_expired_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-expired")
    handshake["timestamp_unix"] = int(time.time()) - 600
    handshake["expires_unix"] = int(time.time()) - 300
    handshake = _resign_handshake(source, handshake)

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_expired"


def test_session_handshake_rejects_tampered_payload(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-tamper", task_id="task-1")
    handshake["task_id"] = "task-2"

    ok, reason = target.verify_session_handshake(handshake, expected_peer_id="node-a", expected_target_peer_id="node-b")
    assert not ok
    assert reason == "handshake_signature_invalid"


def test_session_handshake_rejects_unauthorized_task(tmp_path: Path) -> None:
    source = network_node.PeerNetwork(_config(tmp_path / "source", "node-a"), tmp_path / "source")
    target = network_node.PeerNetwork(_config(tmp_path / "target", "node-b"), tmp_path / "target")
    handshake = source.create_session_handshake(target_peer_id="node-b", session_id="sess-task", task_id="task-a")

    ok, reason = target.verify_session_handshake(
        handshake,
        expected_peer_id="node-a",
        expected_target_peer_id="node-b",
        authorized_task_ids={"task-b"},
    )
    assert not ok
    assert reason == "handshake_task_unauthorized"


def test_mesh_key_bearer_auth_requires_explicit_dev_flag(tmp_path: Path) -> None:
    peer = network_node.PeerNetwork(_config(tmp_path / "peer", "node-a", mesh_key="demo-mesh"), tmp_path / "peer")
    request = _RequestStub({"Authorization": "Bearer demo-mesh"})

    assert not peer._authorize_peer_request(request)

    dev_peer = network_node.PeerNetwork(
        _config(tmp_path / "dev-peer", "node-a", mesh_key="demo-mesh", identity_dev_mesh_auth=True),
        tmp_path / "dev-peer",
    )
    assert dev_peer._authorize_peer_request(request)


def test_signed_peer_auth_accepts_reverse_proxy_original_uri(tmp_path: Path) -> None:
    signer = network_node.PeerNetwork(_config(tmp_path / "signer", "node-a"), tmp_path / "signer")
    verifier = network_node.PeerNetwork(_config(tmp_path / "verifier", "node-b"), tmp_path / "verifier")
    body = network_node.stable_json({"item_id": "result-1"}).encode("utf-8")
    external_path = "/orchestrator/results/dispatch"
    headers = signer._signed_headers("POST", external_path, body)
    proxied_request = _RequestStub(
        {**headers, "X-Silicium-Original-URI": external_path},
        command="POST",
        path="/results/dispatch",
    )

    assert verifier._authorize_peer_request(proxied_request, body)
    assert not verifier._authorize_peer_request(
        _RequestStub(headers, command="POST", path="/results/dispatch"),
        body,
    )
