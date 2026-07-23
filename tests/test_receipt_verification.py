from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import receipt_verification
from workloads.raytracer.run_network_job import validate_compute_receipt


NETWORK_ROOT = Path(__file__).resolve().parents[1]


def _signed_receipt(task_id: str) -> dict[str, object]:
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key = base64.b64encode(public_pem).decode("ascii")
    unsigned: dict[str, object] = {
        "schema": "silicium.compute-receipt.v1",
        "task_id": task_id,
        "billable_work_units": 42,
    }
    return {
        **unsigned,
        "receipt_hash": receipt_verification.sha256_json(unsigned),
        "worker_identity_id": receipt_verification.identity_id_for_key(public_key),
        "worker_public_key": public_key,
        "worker_signature": private_key.sign(
            receipt_verification.stable_json(unsigned).encode("utf-8")
        ).hex(),
    }


def test_raytracer_import_does_not_require_cryptography() -> None:
    script = """
import importlib.abc
import sys

class BlockCryptography(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cryptography" or fullname.startswith("cryptography."):
            raise ModuleNotFoundError("blocked cryptography for runtime smoke test")
        return None

sys.meta_path.insert(0, BlockCryptography())
from workloads.raytracer import run_network_job
assert callable(run_network_job.validate_compute_receipt)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=NETWORK_ROOT,
        env={**os.environ, "PYTHONPATH": str(NETWORK_ROOT)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_compute_receipt_keeps_ed25519_validation() -> None:
    task_id = "fragment-000"
    receipt = _signed_receipt(task_id)

    assert validate_compute_receipt({"compute_receipt": receipt}, task_id) == receipt

    tampered = {**receipt, "billable_work_units": 4_200}
    with pytest.raises(RuntimeError, match="compute_receipt_hash_invalid"):
        validate_compute_receipt({"compute_receipt": tampered}, task_id)


def test_signature_verification_falls_back_to_openssl(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = _signed_receipt("fragment-001")
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "worker_identity_id", "worker_public_key", "worker_signature"}
    }
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["payload"] = Path(command[command.index("-in") + 1]).read_bytes()
        observed["signature"] = Path(command[command.index("-sigfile") + 1]).read_bytes()
        observed["public_key"] = Path(command[command.index("-inkey") + 1]).read_bytes()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(receipt_verification, "_verify_with_cryptography", lambda *_args: None)
    monkeypatch.setattr(receipt_verification.shutil, "which", lambda _name: "/usr/bin/openssl")
    monkeypatch.setattr(receipt_verification.subprocess, "run", fake_run)

    assert receipt_verification.verify_ed25519_signature(
        receipt_verification.stable_json(unsigned).encode("utf-8"),
        str(receipt["worker_signature"]),
        str(receipt["worker_public_key"]),
    )
    assert "pkeyutl" in observed["command"]
    assert observed["payload"] == receipt_verification.stable_json(unsigned).encode("utf-8")
    assert observed["signature"] == bytes.fromhex(str(receipt["worker_signature"]))
    assert observed["public_key"].startswith(b"-----BEGIN PUBLIC KEY-----")


def test_missing_signature_backends_has_an_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    receipt = _signed_receipt("fragment-002")
    monkeypatch.setattr(receipt_verification, "_verify_with_cryptography", lambda *_args: None)
    monkeypatch.setattr(receipt_verification.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="install cryptography or openssl"):
        receipt_verification.verify_ed25519_signature(
            b"payload",
            str(receipt["worker_signature"]),
            str(receipt["worker_public_key"]),
        )
