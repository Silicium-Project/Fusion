"""Signed compute receipts for billable work."""

from __future__ import annotations

from typing import Any

from tools.node.util import safe_id, sha256_json, stable_json


class ReceiptsMixin:
    """Build signed compute receipts."""

    def build_compute_receipt(
        self,
        envelope: dict[str, Any],
        result: dict[str, Any],
        performance: dict[str, Any],
        *,
        started_utc: str,
        finished_utc: str,
    ) -> dict[str, Any]:
        """Signed receipt of the billable work units of one result."""
        task = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        role = str(result.get("role_result", "")).strip().lower()
        width = max(0, int(task.get("x_end", 0) or 0) - int(task.get("x_start", 0) or 0))
        height = max(0, int(task.get("y_end", 0) or 0) - int(task.get("y_start", 0) or 0))
        unit = "deterministic_operation"
        work_units = 0
        if role == "compute" and width > 0 and height > 0:
            unit = "rendered_pixel"
            work_units = width * height
        elif role == "verify" and isinstance(result.get("verification"), dict):
            verification = result["verification"]
            sample_width = max(
                0,
                int(verification.get("sample_x_end", 0) or 0)
                - int(verification.get("sample_x_start", 0) or 0),
            )
            sample_rows = max(0, int(verification.get("sample_rows", 0) or 0))
            unit = "verified_pixel"
            work_units = sample_width * sample_rows
        unsigned = {
            "schema": "silicium.compute-receipt.v1",
            "task_id": safe_id(str(envelope.get("task_id", ""))),
            "root_job_id": safe_id(str(task.get("root_job_id") or task.get("job_id") or "")),
            "worker_node_id": self.config.node_id,
            "role": role or "delegation",
            "workload": str(task.get("workload", "")),
            "billable_work_units": work_units,
            "unit": unit,
            "task_hash": sha256_json(task),
            "result_hash": str(result.get("result_hash", "")),
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "performance": performance,
        }
        receipt_hash = sha256_json(unsigned)
        return {
            **unsigned,
            "receipt_hash": receipt_hash,
            "worker_identity_id": self.peer_network.identity.identity_id,
            "worker_public_key": self.peer_network.identity.public_key_b64,
            "worker_signature": self.peer_network.identity.sign_bytes(stable_json(unsigned).encode("utf-8")),
        }

    def build_receipt_attestation(
        self,
        envelope: dict[str, Any],
        body: dict[str, Any],
        result: dict[str, Any],
        finished_utc: str,
    ) -> dict[str, Any]:
        """Verifier's signed verdict on the compute receipt named in the task body."""
        accepted_receipt_hash = str(body.get("compute_receipt_hash", "")).strip()
        attestation_unsigned = {
            "schema": "silicium.receipt-attestation.v1",
            "task_id": safe_id(str(envelope.get("task_id", ""))),
            "compute_receipt_hash": accepted_receipt_hash,
            "accepted": bool(result.get("choice", result.get("verified", False))),
            "verifier_node_id": self.config.node_id,
            "finished_utc": finished_utc,
        }
        return {
            **attestation_unsigned,
            "verifier_identity_id": self.peer_network.identity.identity_id,
            "verifier_public_key": self.peer_network.identity.public_key_b64,
            "verifier_signature": self.peer_network.identity.sign_bytes(
                stable_json(attestation_unsigned).encode("utf-8")
            ),
        }
