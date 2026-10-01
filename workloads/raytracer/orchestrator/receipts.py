"""Checks of the signed receipts returned by workers.

A compute (or verify) worker signs a `compute_receipt` with its Ed25519
identity; a verifier signs a `receipt_attestation` over the compute receipt
hash. The orchestrator only bills fragments whose receipts and attestation
pass these checks. Each failure raises RuntimeError with a stable
machine-readable code (`<code>:<task_id>`).
"""
from __future__ import annotations

from typing import Any

from tools.receipt_verification import (
    identity_id_for_key,
    sha256_json,
    stable_json,
    verify_ed25519_signature,
)


def validate_compute_receipt(result: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Return the worker's compute receipt after checking hash, identity, signature and task."""
    receipt = result.get("compute_receipt")
    if not isinstance(receipt, dict):
        raise RuntimeError(f"compute_receipt_missing:{task_id}")
    # The hash and the signature cover every field except the signature block itself.
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "worker_identity_id", "worker_public_key", "worker_signature"}
    }
    expected_hash = sha256_json(unsigned)
    if str(receipt.get("receipt_hash", "")) != expected_hash:
        raise RuntimeError(f"compute_receipt_hash_invalid:{task_id}")
    public_key = str(receipt.get("worker_public_key", ""))
    if identity_id_for_key(public_key) != str(receipt.get("worker_identity_id", "")):
        raise RuntimeError(f"compute_receipt_identity_invalid:{task_id}")
    if not verify_ed25519_signature(
        stable_json(unsigned).encode("utf-8"),
        str(receipt.get("worker_signature", "")),
        public_key,
    ):
        raise RuntimeError(f"compute_receipt_signature_invalid:{task_id}")
    if str(receipt.get("task_id", "")) != task_id:
        raise RuntimeError(f"compute_receipt_task_invalid:{task_id}")
    return receipt


def validate_receipt_attestation(
    verify_result: dict[str, Any],
    compute_receipt_hash: str,
    verify_task_id: str,
) -> dict[str, Any]:
    """Return the verifier's attestation after checking it targets the compute receipt and is accepted."""
    attestation = verify_result.get("receipt_attestation")
    if not isinstance(attestation, dict):
        raise RuntimeError(f"receipt_attestation_missing:{verify_task_id}")
    unsigned = {
        key: value
        for key, value in attestation.items()
        if key not in {"verifier_identity_id", "verifier_public_key", "verifier_signature"}
    }
    if str(attestation.get("compute_receipt_hash", "")) != compute_receipt_hash:
        raise RuntimeError(f"receipt_attestation_hash_mismatch:{verify_task_id}")
    public_key = str(attestation.get("verifier_public_key", ""))
    if identity_id_for_key(public_key) != str(attestation.get("verifier_identity_id", "")):
        raise RuntimeError(f"receipt_attestation_identity_invalid:{verify_task_id}")
    if not verify_ed25519_signature(
        stable_json(unsigned).encode("utf-8"),
        str(attestation.get("verifier_signature", "")),
        public_key,
    ):
        raise RuntimeError(f"receipt_attestation_signature_invalid:{verify_task_id}")
    if not bool(attestation.get("accepted", False)):
        verification = verify_result.get("verification")
        if not isinstance(verification, dict):
            verification = {}
        raise RuntimeError(
            f"receipt_attestation_rejected:{verify_task_id}"
            f":verifier={attestation.get('verifier_node_id', '')}"
            f":expected={verification.get('expected_pixel_hash', verify_result.get('expected_hash', ''))}"
            f":recomputed={verification.get('recomputed_pixel_hash', verify_result.get('recomputed_hash', ''))}"
        )
    return attestation
