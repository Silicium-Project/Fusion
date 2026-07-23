from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def identity_id_for_key(public_key_b64: str) -> str:
    try:
        public_pem = base64.b64decode(public_key_b64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError):
        return ""
    return hashlib.sha256(public_pem).hexdigest()[:32]


def _verify_with_cryptography(data: bytes, signature: bytes, public_pem: bytes) -> bool | None:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return None

    try:
        public_key = serialization.load_pem_public_key(public_pem)
        if not isinstance(public_key, Ed25519PublicKey):
            return False
        public_key.verify(signature, data)
        return True
    except Exception:
        return False


def _verify_with_openssl(data: bytes, signature: bytes, public_pem: bytes) -> bool:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("receipt_signature_verifier_unavailable:install cryptography or openssl")

    with tempfile.TemporaryDirectory(prefix="silicium-receipt-") as directory:
        root = Path(directory)
        public_key_path = root / "public.pem"
        payload_path = root / "payload.bin"
        signature_path = root / "signature.bin"
        public_key_path.write_bytes(public_pem)
        payload_path.write_bytes(data)
        signature_path.write_bytes(signature)
        try:
            completed = subprocess.run(
                [
                    openssl,
                    "pkeyutl",
                    "-verify",
                    "-pubin",
                    "-inkey",
                    str(public_key_path),
                    "-rawin",
                    "-in",
                    str(payload_path),
                    "-sigfile",
                    str(signature_path),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"receipt_signature_verifier_failed:{exc}") from exc
    return completed.returncode == 0


def verify_ed25519_signature(data: bytes, signature_hex: str, public_key_b64: str) -> bool:
    if not signature_hex or not public_key_b64:
        return False
    try:
        signature = bytes.fromhex(signature_hex)
        public_pem = base64.b64decode(public_key_b64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError):
        return False

    verified = _verify_with_cryptography(data, signature, public_pem)
    if verified is not None:
        return verified
    return _verify_with_openssl(data, signature, public_pem)
