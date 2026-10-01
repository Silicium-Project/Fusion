"""Signed session handshakes with replay protection."""

from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from tools.node.constants import NETWORK_ROLES
from tools.node.identity import NodeIdentity
from tools.node.util import safe_id, stable_json


class HandshakeMixin:
    """Create and verify signed session handshakes."""

    def create_session_handshake(
        self,
        *,
        target_peer_id: str,
        session_id: str = "",
        purpose: str = "direct_session",
        task_id: str = "",
        candidate_fingerprints: list[dict[str, Any]] | None = None,
        ttl_s: int = 300,
    ) -> dict[str, Any]:
        """Signed handshake proving this node's identity, roles and candidates."""
        now = int(time.time())
        handshake = {
            "schema_version": 1,
            "message_type": "session_handshake",
            "session_id": session_id or "sess-" + uuid.uuid4().hex,
            "peer_id": self.node_id,
            "target_peer_id": safe_id(target_peer_id),
            "purpose": safe_id(purpose),
            "task_id": str(task_id or ""),
            "roles": sorted(self.config.roles),
            "reputation_score": self.local_reputation_score,
            "resource_reputation": self.local_resource_reputation,
            "onchain_reputation": self.local_onchain_reputation,
            "candidate_fingerprints": candidate_fingerprints or [],
            "timestamp_unix": now,
            "expires_unix": now + max(1, int(ttl_s)),
            "nonce": uuid.uuid4().hex,
            "identity_id": self.identity.identity_id,
            "public_key": self.identity.public_key_b64,
        }
        handshake["signature"] = self.identity.sign_bytes(stable_json(handshake).encode("utf-8"))
        return handshake

    def verify_session_handshake(
        self,
        handshake: Mapping[str, Any] | None,
        *,
        expected_peer_id: str = "",
        expected_target_peer_id: str = "",
        authorized_task_ids: set[str] | None = None,
        max_age_s: int = 300,
    ) -> tuple[bool, str]:
        """Validate a handshake; return ``(ok, reason)``. Records its nonce on success.

        Checks run in a fixed order (identity, signature, peers, freshness,
        task, roles, reputation, candidates, nonce, replay) and the first
        failing check gives the reason.
        """
        if not isinstance(handshake, Mapping):
            return False, "handshake_not_object"
        if str(handshake.get("message_type", "")) != "session_handshake":
            return False, "handshake_type_invalid"
        reason = self._handshake_identity_error(handshake)
        if reason:
            return False, reason
        peer_id = safe_id(str(handshake.get("peer_id", "")))
        target_peer_id = safe_id(str(handshake.get("target_peer_id", "")))
        if expected_peer_id and peer_id != safe_id(expected_peer_id):
            return False, "handshake_peer_mismatch"
        if expected_target_peer_id and target_peer_id != safe_id(expected_target_peer_id):
            return False, "handshake_target_mismatch"
        now = int(time.time())
        try:
            timestamp_unix = int(handshake.get("timestamp_unix", 0) or 0)
            expires_unix = int(handshake.get("expires_unix", 0) or 0)
        except (TypeError, ValueError):
            return False, "handshake_timestamp_invalid"
        if timestamp_unix <= 0 or abs(now - timestamp_unix) > max(1, int(max_age_s)):
            return False, "handshake_expired"
        if expires_unix <= now:
            return False, "handshake_expired"
        task_id = str(handshake.get("task_id", "") or "")
        if authorized_task_ids is not None and task_id not in authorized_task_ids:
            return False, "handshake_task_unauthorized"
        reason = self._handshake_claims_error(handshake, now, expires_unix)
        if reason:
            return False, reason
        nonce = str(handshake.get("nonce", "")).strip()
        session_id = str(handshake.get("session_id", "")).strip()
        if not nonce or not session_id:
            return False, "handshake_nonce_missing"
        replay_key = f"{str(handshake.get('identity_id', '')).strip()}:{session_id}:{nonce}"
        self._prune_handshake_nonces(now)
        with self._lock:
            if replay_key in self._seen_handshake_nonces:
                return False, "handshake_replay"
            self._seen_handshake_nonces[replay_key] = float(expires_unix)
        return True, "ok"

    @staticmethod
    def _handshake_identity_error(handshake: Mapping[str, Any]) -> str:
        """Empty string when the handshake is signed by the key it announces."""
        public_key = str(handshake.get("public_key", "")).strip()
        identity_id = str(handshake.get("identity_id", "")).strip()
        signature = str(handshake.get("signature", "")).strip()
        if not public_key or not identity_id or not signature:
            return "handshake_identity_missing"
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return "handshake_identity_mismatch"
        unsigned = dict(handshake)
        unsigned.pop("signature", None)
        if not NodeIdentity.verify_bytes(stable_json(unsigned).encode("utf-8"), signature, public_key):
            return "handshake_signature_invalid"
        return ""

    @staticmethod
    def _handshake_claims_error(handshake: Mapping[str, Any], now: int, expires_unix: int) -> str:
        """Empty string when roles, reputation and candidate fingerprints are valid."""
        roles = handshake.get("roles", [])
        if not isinstance(roles, list) or not roles:
            return "handshake_roles_invalid"
        role_set = {str(role).lower() for role in roles}
        if not role_set.issubset(NETWORK_ROLES):
            return "handshake_roles_invalid"
        try:
            float(handshake.get("reputation_score", 0.0) or 0.0)
        except (TypeError, ValueError):
            return "handshake_reputation_invalid"
        candidates = handshake.get("candidate_fingerprints", [])
        if not isinstance(candidates, list):
            return "handshake_candidates_invalid"
        for candidate in candidates:
            if not isinstance(candidate, dict):
                return "handshake_candidates_invalid"
            try:
                candidate_expires = int(candidate.get("expires_unix", expires_unix) or expires_unix)
            except (TypeError, ValueError):
                return "handshake_candidates_invalid"
            if candidate_expires <= now:
                return "handshake_candidate_expired"
        return ""

    def _prune_handshake_nonces(self, now: int | None = None) -> None:
        cutoff = float(now if now is not None else int(time.time()))
        with self._lock:
            for key, expires_at in list(self._seen_handshake_nonces.items()):
                if float(expires_at) <= cutoff:
                    self._seen_handshake_nonces.pop(key, None)
