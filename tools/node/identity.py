"""Ed25519 node identity: key management, signing and signature verification."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from tools.node.config import NodeConfig
from tools.node.util import sha256_bytes


class NodeIdentity:
    """Ed25519 key pair of a node; ``identity_id`` is a hash of the public key."""

    def __init__(self, config: NodeConfig) -> None:
        default_key = config.state_dir / "peer_identity_ed25519.pem"
        self.private_key_path = Path(config.identity_key_path).expanduser() if str(config.identity_key_path).strip() else default_key
        self.public_key_path = self.private_key_path.with_suffix(".pub.pem")
        self.private_key_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_keypair()
        self._harden_private_key_permissions()
        public_pem = self.public_key_path.read_bytes()
        self._private_key = serialization.load_pem_private_key(
            self.private_key_path.read_bytes(),
            password=None,
        )
        if not isinstance(self._private_key, Ed25519PrivateKey):
            raise RuntimeError("identity_private_key_is_not_ed25519")
        self.public_key_b64 = base64.b64encode(public_pem).decode("ascii")
        self.identity_id = sha256_bytes(public_pem)[:32]

    def sign_bytes(self, data: bytes) -> str:
        """Hex Ed25519 signature of ``data``."""
        return self._private_key.sign(data).hex()

    @staticmethod
    def verify_bytes(data: bytes, signature_hex: str, public_key_b64: str) -> bool:
        """Verify a hex signature against a base64 PEM public key."""
        if not signature_hex or not public_key_b64:
            return False
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
            signature = bytes.fromhex(signature_hex)
            public_key = serialization.load_pem_public_key(public_pem)
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            public_key.verify(signature, data)
            return True
        except Exception:
            return False

    @staticmethod
    def identity_id_for_key(public_key_b64: str) -> str:
        """Identity id (sha256 prefix) of a base64 PEM public key, or ""."""
        try:
            public_pem = base64.b64decode(public_key_b64.encode("ascii"))
        except Exception:
            return ""
        return sha256_bytes(public_pem)[:32]

    def _ensure_keypair(self) -> None:
        if self.public_key_path.exists():
            try:
                legacy_marker = self.public_key_path.read_text(encoding="utf-8").startswith("SILICIUM-HMAC-SHA256:")
            except OSError:
                legacy_marker = False
            if legacy_marker:
                for path in (self.private_key_path, self.public_key_path):
                    if path.exists():
                        backup = path.with_name(path.name + ".legacy-hmac")
                        try:
                            path.replace(backup)
                        except OSError:
                            path.unlink(missing_ok=True)
        if not self.private_key_path.exists():
            private_key = Ed25519PrivateKey.generate()
            self.private_key_path.write_bytes(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        if not self.public_key_path.exists():
            private_key = serialization.load_pem_private_key(
                self.private_key_path.read_bytes(),
                password=None,
            )
            if not isinstance(private_key, Ed25519PrivateKey):
                raise RuntimeError("identity_private_key_is_not_ed25519")
            self.public_key_path.write_bytes(
                private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            )

    def _harden_private_key_permissions(self) -> None:
        if os.name == "nt":
            return
        try:
            os.chmod(self.private_key_path, 0o600)
        except OSError:
            pass
