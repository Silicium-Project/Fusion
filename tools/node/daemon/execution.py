"""Task/request execution bodies and outcome accounting (metrics, retries, reputation, gossip)."""

from __future__ import annotations

import time
from typing import Any

from tools.node.util import (
    append_jsonl,
    sha256_bytes,
    sha256_json,
    stable_json,
    utc_now,
)


class ExecutionMixin:
    """Execute task and request bodies and account for the outcome."""

    def schedule_retry_or_dead_letter(self, envelope: dict[str, Any], error: str) -> None:
        """Re-queue a failed envelope (``retries.ndjson``) or dead-letter it."""
        attempt = int(envelope.get("attempt", 0) or 0)
        next_envelope = dict(envelope)
        next_envelope["last_error"] = error
        next_envelope["last_error_utc"] = utc_now()
        if attempt < self.config.max_retries:
            next_envelope["attempt"] = attempt + 1
            next_envelope["status"] = "retrying"
            append_jsonl(self.config.export_dir / "retries.ndjson", next_envelope)
            self.metrics["retried"] = int(self.metrics.get("retried", 0) or 0) + 1
            return
        next_envelope["status"] = "dead_lettered"
        append_jsonl(self.config.export_dir / "dead_letters.ndjson", next_envelope)
        self.metrics["dead_lettered"] = int(self.metrics.get("dead_lettered", 0) or 0) + 1

    def update_reputation(self, ok: bool, kind: str, result: dict[str, Any]) -> None:
        """Adjust local reputation and the resource memory after an execution."""
        if ok:
            delta = 0.25
            if kind == "request" and bool(result.get("choice", True)):
                delta += 0.1
            if kind == "task" and isinstance(result.get("replication"), dict) and result["replication"].get("satisfied") is True:
                delta += 0.15
            score = self.reputation.adjust_local(delta, f"{kind}_success")
        else:
            score = self.reputation.adjust_local(-0.5, f"{kind}_failure")
        role = str(result.get("role_result", "")).strip().lower()
        if role not in {"compute", "verify", "storage"}:
            role = "delegation"
        integrity_violation = bool(result.get("integrity_violation") or result.get("proof_invalid") or result.get("hash_mismatch"))
        event_class = "integrity" if integrity_violation else ("verified" if ok else "transient")
        self.reputation.observe_resource(role, ok, event_class=event_class)
        input_metadata = result.get("input") if isinstance(result.get("input"), dict) else {}
        if str(input_metadata.get("source", "")).startswith("silicium-"):
            self.reputation.observe_resource("connection", ok, event_class="verified" if ok else "transient", weight=0.5)
        self.config.reputation_score = score  # keep announced score aligned

    def handle_task(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Fetch the input, run the task for this node's role and publish its output."""
        task = dict(envelope.get("task")) if isinstance(envelope.get("task"), dict) else {}
        task["_runtime_progress_path"] = str(envelope.get("_runtime_progress_path", ""))
        self.update_active_task(phase="fetching_input", progress_percent=2.0, progress_source="measured")
        inline_input = task.get("inline_input")
        if isinstance(inline_input, dict):
            p2p_data = stable_json(inline_input).encode("utf-8")
            p2p_meta = {"source": "inline-task", "size_bytes": len(p2p_data)}
        else:
            p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        self.update_active_task(
            phase="executing",
            progress_percent=10.0,
            progress_source="estimated",
            input_bytes=len(p2p_data),
        )
        role_output = self.runtime.run_task(envelope, task, p2p_data, p2p_meta)
        self.update_active_task(phase="publishing_result", progress_percent=92.0)
        output = {
            "success": True,
            "envelope_kind": "task",
            "task_id": envelope.get("task_id", ""),
            "required_roles": envelope.get("required_roles", []),
            "priority": envelope.get("priority", "normal"),
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            **role_output,
        }
        output["result_hash"] = str(role_output.get("result_hash") or sha256_json(output))
        # Workloads such as raytracer publish their actual binary artifact.
        # Preserve that reference instead of replacing it with this JSON
        # manifest; downstream reassembly expects the PPM bytes themselves.
        output_ref = role_output.get("output_ref") if isinstance(role_output.get("output_ref"), dict) else None
        if output_ref is None:
            output_ref = self.p2p.put_local(stable_json(output).encode("utf-8"))
        self.update_active_task(phase="finalizing", progress_percent=98.0)
        output["output_ref"] = output_ref
        output["proof_ref"] = role_output.get("proof_ref") if isinstance(role_output.get("proof_ref"), dict) else output_ref
        on_chain = self.submit_task_on_chain(envelope, task, output, output_ref)
        if on_chain:
            output["on_chain"] = on_chain
        return output

    def handle_request(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Fetch the input, answer the request and publish the response."""
        request = envelope.get("request") if isinstance(envelope.get("request"), dict) else {}
        self.update_active_task(phase="fetching_input", progress_percent=2.0, progress_source="measured")
        p2p_data, p2p_meta = self.p2p.fetch(envelope.get("p2p_ref"))
        self.update_active_task(
            phase="executing",
            progress_percent=10.0,
            progress_source="estimated",
            input_bytes=len(p2p_data),
        )
        request_kind = str(envelope.get("kind", "request"))
        role_response = self.runtime.run_request(envelope, request, p2p_data, p2p_meta)
        self.update_active_task(phase="publishing_result", progress_percent=92.0)
        response = {
            "success": True,
            "envelope_kind": "request",
            "request_id": envelope.get("request_id", ""),
            "kind": request_kind,
            "priority": envelope.get("priority", "high"),
            "target_roles": envelope.get("target_roles", []),
            "job_id": envelope.get("job_id", ""),
            "fragment_id": envelope.get("fragment_id", ""),
            "input": p2p_meta,
            "input_hash": sha256_bytes(p2p_data),
            **role_response,
        }
        response_ref = self.p2p.put_local(stable_json(response).encode("utf-8"))
        self.update_active_task(phase="finalizing", progress_percent=98.0)
        response["response_ref"] = response_ref
        on_chain = self.submit_request_on_chain(envelope, response, response_ref)
        if on_chain:
            response["on_chain"] = on_chain
        return response

    def _record_outcome_metrics(
        self,
        envelope: dict[str, Any],
        ok: bool,
        cancelled: bool,
        timed_out: bool,
        error: str,
        safe_item: str,
        duration_ms: int,
    ) -> None:
        """Update counters; schedule a retry on failure, broadcast expiry on timeout."""
        if ok:
            self.metrics["handled"] = int(self.metrics.get("handled", 0) or 0) + 1
        elif not cancelled and not timed_out:
            self.metrics["failed"] = int(self.metrics.get("failed", 0) or 0) + 1
            self.schedule_retry_or_dead_letter(envelope, error)
        elif timed_out:
            timeout_control = {
                "control_id": f"{safe_item}-expire-{int(time.time() * 1000)}",
                "root_job_id": safe_item,
                "action": "expire",
                "reason": error,
                "issuer_node_id": self.config.node_id,
                "issued_utc": utc_now(),
            }
            self.apply_task_control(timeout_control, signed_by=self.config.node_id)
            self.peer_network.publish("task_control", timeout_control, background=True)
        self.metrics["duration_total_ms"] = int(self.metrics.get("duration_total_ms", 0) or 0) + duration_ms
        self.metrics["duration_max_ms"] = max(int(self.metrics.get("duration_max_ms", 0) or 0), duration_ms)
        self.metrics["last_duration_ms"] = duration_ms
        handled_total = max(1, int(self.metrics.get("handled", 0) or 0) + int(self.metrics.get("failed", 0) or 0))
        self.metrics["duration_average_ms"] = round(
            int(self.metrics.get("duration_total_ms", 0) or 0) / handled_total, 2
        )

    def _publish_task_outcome(self, safe_item: str, body: dict[str, Any], result: dict[str, Any]) -> None:
        """Best-effort gossip of a successful task (and verify handoff)."""
        self.peer_network.publish(
            "fragment_result",
            {
                "item_id": safe_item,
                "result_hash": result.get("result_hash", ""),
                "proof_ref": result.get("proof_ref", {}),
            },
            background=True,
        )
        if str(result.get("role_result", "")).strip().lower() == "verify":
            self.peer_network.publish(
                "worker_handoff",
                {
                    "item_id": safe_item,
                    "source_task_id": str(body.get("source_task_id", "")),
                    "compute_node_id": str(body.get("source_node_id", "")),
                    "verify_node_id": self.config.node_id,
                    "content_id": str(
                        (body.get("source_output_ref") or {}).get("content_id", "")
                        if isinstance(body.get("source_output_ref"), dict)
                        else ""
                    ),
                    "receipt_hash": str(body.get("compute_receipt_hash", "")),
                    "verified": bool(result.get("choice", result.get("verified", False))),
                },
                background=True,
            )
