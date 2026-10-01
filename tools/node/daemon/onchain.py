"""On-chain submission of task and request outcomes."""

from __future__ import annotations

from typing import Any

from tools.node.util import fragment_status_name, stable_json


class OnchainSubmitMixin:
    """Submit results, votes and finalisation to the Solana program."""

    def envelope_on_chain(self, envelope: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        """``on_chain`` block of the envelope, else of its body, else ``{}``."""
        on_chain = envelope.get("on_chain")
        if not isinstance(on_chain, dict):
            on_chain = body.get("on_chain")
        return on_chain if isinstance(on_chain, dict) else {}

    def fetch_fragment_state(self, on_chain: dict[str, Any]) -> dict[str, Any]:
        """On-chain fragment account referenced by ``on_chain`` (``{}`` when disabled)."""
        if not self.config.solana_enable:
            return {}
        params: dict[str, Any] = {}
        if on_chain.get("fragment"):
            params["fragment"] = on_chain.get("fragment")
        else:
            params["job"] = on_chain.get("job")
            params["fragment_index"] = on_chain.get("fragment_index", on_chain.get("fragmentIndex"))
        snapshot = self.solana.call("fetch_fragment", params)
        account = snapshot.get("account")
        return account if isinstance(account, dict) else {}

    def submit_task_on_chain(
        self,
        envelope: dict[str, Any],
        task: dict[str, Any],
        output: dict[str, Any],
        output_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Declare storage, submit the fragment result and/or finalise the job.

        Failures are recorded and swallowed unless ``on_chain.required``.
        """
        on_chain = self.envelope_on_chain(envelope, task)
        if not on_chain:
            return []

        submitted: list[dict[str, Any]] = []
        required = bool(on_chain.get("required") or envelope.get("on_chain_required"))
        roles = {str(role).lower() for role in envelope.get("required_roles", [])}
        task_kind = str(task.get("kind", "")).lower()
        proof_ref = output_ref.get("hash") or stable_json(output_ref)

        try:
            if ("storage" in roles or task_kind == "storage") and on_chain.get("job"):
                submitted.append(self._declare_storage_on_chain(on_chain, output, proof_ref))
            if ("compute" in roles or task_kind == "compute") and on_chain.get("job") and on_chain.get("worker_token"):
                fragment_index = on_chain.get("fragment_index", on_chain.get("fragmentIndex"))
                if fragment_index is not None:
                    submitted.append(self._submit_fragment_on_chain(on_chain, fragment_index, output, proof_ref))
            if on_chain.get("finalize") and on_chain.get("job") and on_chain.get("escrow") and on_chain.get("client_token"):
                submitted.append(self._finalize_job_on_chain(on_chain, output, output_ref))
        except Exception as exc:
            if required:
                raise
            submitted.append({"ok": False, "skipped": False, "error": "optional_on_chain_failed", "details": str(exc)})

        if required and not submitted:
            raise ValueError("on_chain_required_but_no_supported_task_operation")
        return submitted

    def _declare_storage_on_chain(self, on_chain: dict[str, Any], output: dict[str, Any], proof_ref: Any) -> dict[str, Any]:
        return self.solana.call(
            "declare_storage",
            {
                "job": on_chain.get("job"),
                "manifest_hash": on_chain.get("manifest_hash") or output.get("manifest_hash") or output.get("result_hash"),
                "input_root_hash": on_chain.get("input_root_hash") or output.get("input_hash") or output.get("result_hash"),
                "storage_ref_hash": on_chain.get("storage_ref_hash") or proof_ref,
                "encryption_ref_hash": on_chain.get("encryption_ref_hash"),
            },
        )

    def _submit_fragment_on_chain(
        self,
        on_chain: dict[str, Any],
        fragment_index: Any,
        output: dict[str, Any],
        proof_ref: Any,
    ) -> dict[str, Any]:
        """Claim+submit, submit only, or skip, depending on the fragment state."""
        fragment_state = self.fetch_fragment_state(on_chain)
        status = fragment_status_name(fragment_state) if fragment_state else "unknown"
        op = "claim_and_submit_fragment"
        if status == "claimed":
            op = "submit_fragment_result"
        elif status in {"submitted", "verified", "finalized", "resolved"}:
            op = ""
        elif bool(on_chain.get("skip_claim")):
            op = "submit_fragment_result"
        if op:
            params = {
                "job": on_chain.get("job"),
                "fragment_index": int(fragment_index),
                "worker_token": on_chain.get("worker_token"),
                "result_hash": output.get("result_hash"),
                "proof_ref": proof_ref,
                "skip_claim": bool(on_chain.get("skip_claim")),
            }
            if op == "submit_fragment_result":
                params["skip_claim"] = True
        return self.solana.call(op, params) if op else {"ok": True, "skipped": True, "reason": "fragment_already_submitted"}

    def _finalize_job_on_chain(self, on_chain: dict[str, Any], output: dict[str, Any], output_ref: dict[str, Any]) -> dict[str, Any]:
        return self.solana.call(
            "finalize_job",
            {
                "job": on_chain.get("job"),
                "escrow": on_chain.get("escrow"),
                "client_token": on_chain.get("client_token"),
                "final_hash": on_chain.get("final_hash") or output.get("result_hash"),
                "output_uri": on_chain.get("output_uri") or output_ref.get("content_id") or stable_json(output_ref),
            },
        )

    def submit_request_on_chain(
        self,
        envelope: dict[str, Any],
        response: dict[str, Any],
        response_ref: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Vote on a fragment (and claim the verifier reward) for audit/verify requests."""
        request = envelope.get("request") if isinstance(envelope.get("request"), dict) else {}
        on_chain = self.envelope_on_chain(envelope, request)
        if not on_chain:
            return []

        submitted: list[dict[str, Any]] = []
        required = bool(on_chain.get("required") or envelope.get("on_chain_required"))
        request_kind = str(envelope.get("kind", "")).lower()
        target_roles = {str(role).lower() for role in envelope.get("target_roles", [])}
        should_vote = request_kind in {"audit", "challenge", "verify"} or bool({"audit", "verify"}.intersection(target_roles))

        try:
            if should_vote and on_chain.get("job") and on_chain.get("escrow") and on_chain.get("worker_token"):
                params = {
                    "job": on_chain.get("job"),
                    "fragment": on_chain.get("fragment"),
                    "fragment_index": on_chain.get("fragment_index", on_chain.get("fragmentIndex")),
                    "escrow": on_chain.get("escrow"),
                    "worker_token": on_chain.get("worker_token"),
                    "choice": on_chain.get("choice", request.get("choice", response.get("choice", True))),
                    "compute_worker": on_chain.get("compute_worker"),
                    "round": on_chain.get("round"),
                    "response_ref": response_ref.get("hash") or stable_json(response_ref),
                    "response_hash": response.get("input_hash"),
                }
                submitted.append(self.solana.call("vote_fragment", params))
                if on_chain.get("claim_reward"):
                    submitted.append(
                        self.solana.call(
                            "claim_verifier_reward",
                            {
                                "job": on_chain.get("job"),
                                "fragment": on_chain.get("fragment"),
                                "escrow": on_chain.get("escrow"),
                                "verifier_token": on_chain.get("verifier_token") or on_chain.get("worker_token"),
                                "round": on_chain.get("round"),
                            },
                        )
                    )
        except Exception as exc:
            if required:
                raise
            submitted.append({"ok": False, "skipped": False, "error": "optional_on_chain_failed", "details": str(exc)})

        if required and not submitted:
            raise ValueError("on_chain_required_but_no_supported_request_operation")
        return submitted
