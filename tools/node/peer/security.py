"""Message signing (Ed25519 + optional mesh HMAC) and signed HTTP request auth."""

from __future__ import annotations

import hashlib
import hmac
import http.server
import time
from typing import Any

from tools.node.identity import NodeIdentity
from tools.node.util import sha256_bytes, stable_json


class SecurityMixin:
    """Sign and verify mesh messages and peer HTTP requests."""

    def _signed_headers(self, method: str, path: str, body: bytes, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self.config.mesh_key:
            headers["Authorization"] = f"Bearer {self.config.mesh_key}"
        timestamp = str(int(time.time()))
        body_hash = sha256_bytes(body)
        signing_payload = "\n".join([method.upper(), path, timestamp, body_hash, self.node_id, self.identity.identity_id]).encode("utf-8")
        headers.update(
            {
                "X-Silicium-Node-Id": self.node_id,
                "X-Silicium-Identity-Id": self.identity.identity_id,
                "X-Silicium-Public-Key": self.identity.public_key_b64,
                "X-Silicium-Timestamp": timestamp,
                "X-Silicium-Body-Hash": body_hash,
                "X-Silicium-Signature": self.identity.sign_bytes(signing_payload),
            }
        )
        return headers

    def _sign_message(self, message: dict[str, Any]) -> None:
        unsigned = dict(message)
        unsigned["identity_id"] = self.identity.identity_id
        unsigned["public_key"] = self.identity.public_key_b64
        unsigned["node_id"] = self.node_id
        if self.config.mesh_key:
            unsigned.pop("mesh_mac", None)
            unsigned["mesh_mac"] = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
        unsigned.pop("mesh_mac", None)
        unsigned.pop("signature", None)
        message.update(unsigned)
        message["signature"] = self.identity.sign_bytes(stable_json(unsigned).encode("utf-8"))
        if self.config.mesh_key:
            message["mesh_mac"] = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()

    def _verify_message(self, message: dict[str, Any]) -> bool:
        public_key = str(message.get("public_key", "")).strip()
        signature = str(message.get("signature", "")).strip()
        identity_id = str(message.get("identity_id", "")).strip()
        if public_key and signature:
            if NodeIdentity.identity_id_for_key(public_key) != identity_id:
                return False
            unsigned = dict(message)
            unsigned.pop("signature", None)
            unsigned.pop("mesh_mac", None)
            if not NodeIdentity.verify_bytes(stable_json(unsigned).encode("utf-8"), signature, public_key):
                return False
        elif self.config.mesh_key:
            return False
        if self.config.mesh_key:
            received = str(message.get("mesh_mac", "")).strip()
            if not received:
                return False
            unsigned = dict(message)
            unsigned.pop("signature", None)
            unsigned.pop("mesh_mac", None)
            expected = hmac.new(self.config.mesh_key.encode("utf-8"), stable_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(received, expected):
                return False
        return True

    def _authorize_peer_request(self, handler: http.server.BaseHTTPRequestHandler, body: bytes = b"") -> bool:
        if self.config.mesh_key and self.config.identity_dev_mesh_auth:
            auth = str(handler.headers.get("Authorization", "")).strip()
            if auth == f"Bearer {self.config.mesh_key}":
                return True
        public_key = str(handler.headers.get("X-Silicium-Public-Key", "")).strip()
        signature = str(handler.headers.get("X-Silicium-Signature", "")).strip()
        identity_id = str(handler.headers.get("X-Silicium-Identity-Id", "")).strip()
        timestamp = str(handler.headers.get("X-Silicium-Timestamp", "")).strip()
        body_hash = str(handler.headers.get("X-Silicium-Body-Hash", "")).strip()
        node_id = str(handler.headers.get("X-Silicium-Node-Id", "")).strip()
        if not public_key or not signature or not identity_id or not timestamp or not node_id:
            return False
        if NodeIdentity.identity_id_for_key(public_key) != identity_id:
            return False
        try:
            ts = int(timestamp)
        except ValueError:
            return False
        if abs(int(time.time()) - ts) > 300:
            return False
        if body_hash != sha256_bytes(body):
            return False
        signed_paths = [str(handler.path)]
        original_uri = str(handler.headers.get("X-Silicium-Original-URI", "")).strip()
        if original_uri.startswith("/") and len(original_uri) <= 4096 and original_uri not in signed_paths:
            signed_paths.append(original_uri)
        for signed_path in signed_paths:
            signing_payload = "\n".join([handler.command.upper(), signed_path, timestamp, body_hash, node_id, identity_id]).encode("utf-8")
            if NodeIdentity.verify_bytes(signing_payload, signature, public_key):
                return True
        return False
