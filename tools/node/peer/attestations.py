"""Signed transport-path attestations: record, verify, persist and list."""

from __future__ import annotations

import hmac
import threading
import time
from typing import Any, Mapping

from tools.node.identity import NodeIdentity
from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    read_json,
    safe_id,
    sha256_bytes,
    stable_json,
    utc_now,
)


# Candidate-pair keys kept in an attestation (the full candidates stay local).
_ATTESTED_PAIR_FIELDS = {
    "local_candidate_id",
    "remote_candidate_id",
    "ack_local_candidate_id",
    "ack_remote_candidate_id",
    "local_candidate_type",
    "remote_candidate_type",
}


class AttestationsMixin:
    """Produce and verify signed proofs of which transport route carried data."""

    def record_transport_attestation(
        self,
        *,
        route: str,
        transport_backend: str,
        remote_peer_id: str = "",
        session_id: str = "",
        proof_scope: str = "connectivity_check",
        task_id: str = "",
        content_id: str = "",
        content_sha256: str = "",
        size_bytes: int = 0,
        endpoint: str = "",
        relay_peer_id: str = "",
        selected_candidate_pair: Mapping[str, Any] | None = None,
        peer_proof: Mapping[str, Any] | None = None,
        success: bool = True,
        failure_reason: str = "",
    ) -> dict[str, Any]:
        """Sign, store and journal a claim about the route that carried data."""
        normalized_route = safe_id(str(route)).lower()
        if normalized_route not in {"direct", "relay", "central", "failed"}:
            raise ValueError(f"unsupported_transport_route:{normalized_route}")
        normalized_remote = self._optional_peer_id(remote_peer_id)
        pair = selected_candidate_pair if isinstance(selected_candidate_pair, Mapping) else {}
        proof = peer_proof if isinstance(peer_proof, Mapping) else {}
        peer_proof_hash, peer_proof_verified = self._peer_proof_status(proof, normalized_remote)
        claim = {
            "schema_version": 1,
            "attestation_type": "silicium.transport-path",
            "observer_peer_id": self.node_id,
            "observer_identity_id": self.identity.identity_id,
            "observer_public_key": self.identity.public_key_b64,
            "remote_peer_id": normalized_remote,
            "route": normalized_route,
            "transport_backend": safe_id(str(transport_backend)).lower(),
            "proof_scope": safe_id(str(proof_scope)).lower(),
            "session_id": str(session_id).strip(),
            "task_id": self._optional_peer_id(task_id),
            "content_id": str(content_id).strip(),
            "content_sha256": str(content_sha256).removeprefix("sha256:").strip().lower(),
            "size_bytes": max(0, int(size_bytes)),
            "endpoint": str(endpoint).strip(),
            "relay_peer_id": self._optional_peer_id(relay_peer_id),
            "selected_candidate_pair": {
                str(key): value for key, value in pair.items() if str(key) in _ATTESTED_PAIR_FIELDS
            },
            "peer_proof_hash": peer_proof_hash,
            "peer_proof_verified": peer_proof_verified,
            "success": bool(success),
            "failure_reason": safe_id(str(failure_reason)).lower() if failure_reason else "",
            "timestamp_unix": int(time.time()),
            "timestamp_utc": utc_now(),
        }
        return self._sign_and_store_attestation(claim)

    def _peer_proof_status(self, proof: Mapping[str, Any], normalized_remote: str) -> tuple[str, bool]:
        """Hash of the remote peer's proof and whether it is signed by that peer."""
        peer_proof_hash = sha256_bytes(stable_json(dict(proof)).encode("utf-8")) if proof else ""
        peer_proof_verified = bool(
            proof
            and proof.get("signature")
            and proof.get("public_key")
            and self._verify_message(dict(proof))
            and (
                not normalized_remote
                or safe_id(str(proof.get("node_id") or proof.get("source_peer_id") or "")) == normalized_remote
            )
        )
        return peer_proof_hash, peer_proof_verified

    def _sign_and_store_attestation(self, claim: dict[str, Any]) -> dict[str, Any]:
        claim_hash = sha256_bytes(stable_json(claim).encode("utf-8"))
        attestation = {
            **claim,
            "claim_hash": claim_hash,
            "signature": self.identity.sign_bytes(stable_json(claim).encode("utf-8")),
        }
        with self._lock:
            if not any(item.get("claim_hash") == claim_hash for item in self._transport_attestations):
                self._transport_attestations.append(attestation)
                self._transport_attestations = self._transport_attestations[-128:]
        append_jsonl(self.transport_attestation_events_path, attestation)
        self.transport_attestations_snapshot()
        return dict(attestation)

    def record_transport_attestation_background(self, **claim: Any) -> None:
        """Record an attestation in a daemon thread (errors ignored)."""
        def _record() -> None:
            try:
                self.record_transport_attestation(**claim)
            except (OSError, RuntimeError, ValueError):
                return

        threading.Thread(
            target=_record,
            name=f"transport-attestation-{self.node_path_id}",
            daemon=True,
        ).start()

    @staticmethod
    def verify_transport_attestation(attestation: Mapping[str, Any]) -> bool:
        """Check identity, claim hash and signature of an attestation."""
        if not isinstance(attestation, Mapping):
            return False
        signature = str(attestation.get("signature", "")).strip()
        claim_hash = str(attestation.get("claim_hash", "")).strip().lower()
        public_key = str(attestation.get("observer_public_key", "")).strip()
        identity_id = str(attestation.get("observer_identity_id", "")).strip()
        route = str(attestation.get("route", "")).strip().lower()
        if not signature or not claim_hash or route not in {"direct", "relay", "central", "failed"}:
            return False
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return False
        claim = dict(attestation)
        claim.pop("signature", None)
        claim.pop("claim_hash", None)
        encoded = stable_json(claim).encode("utf-8")
        return AttestationsMixin._transport_attestation_hash_valid(attestation) and NodeIdentity.verify_bytes(encoded, signature, public_key)

    @staticmethod
    def _transport_attestation_hash_valid(attestation: Mapping[str, Any]) -> bool:
        claim_hash = str(attestation.get("claim_hash", "")).strip().lower()
        if not claim_hash:
            return False
        claim = dict(attestation)
        claim.pop("signature", None)
        claim.pop("claim_hash", None)
        return hmac.compare_digest(
            sha256_bytes(stable_json(claim).encode("utf-8")),
            claim_hash,
        )

    def recent_transport_attestations(self, limit: int = 8) -> list[dict[str, Any]]:
        """Newest attestations first, at most ``limit``."""
        with self._lock:
            ordered = sorted(
                self._transport_attestations,
                key=lambda item: (int(item.get("timestamp_unix", 0) or 0), str(item.get("claim_hash", ""))),
                reverse=True,
            )
        return [dict(item) for item in ordered[: max(0, int(limit))]]

    def transport_attestations_snapshot(self) -> dict[str, Any]:
        """Persist and return the last 128 attestations."""
        attestations = self.recent_transport_attestations(128)
        payload = {
            "schema_version": 1,
            "node_id": self.node_id,
            "count": len(attestations),
            "attestations": attestations,
            "updated_utc": utc_now(),
        }
        atomic_write_json(self.transport_attestations_path, payload)
        return payload

    def _load_transport_attestations(self) -> None:
        snapshot = read_json(self.transport_attestations_path, {})
        attestations = snapshot.get("attestations") if isinstance(snapshot, dict) else None
        if not isinstance(attestations, list):
            return
        verified = [
            dict(attestation)
            for attestation in attestations
            if isinstance(attestation, Mapping)
            and str(attestation.get("observer_peer_id", "")) == self.node_id
            and self.verify_transport_attestation(attestation)
        ]
        with self._lock:
            self._transport_attestations = verified[-128:]
