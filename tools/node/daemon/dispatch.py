"""Remote dispatch to peers and return/ingestion of dispatched results."""

from __future__ import annotations

import base64
import hashlib
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from tools.node.config import _peer_constraints
from tools.node.envelopes import ingest_content_blobs
from tools.node.util import (
    append_jsonl,
    atomic_write_json,
    optional_peer_id,
    read_json,
    safe_id,
    safe_path_id,
    stable_json,
    utc_now,
)


class DispatchMixin:
    """Push work to peers and route their results back."""

    def try_remote_dispatch(self, envelope: dict[str, Any]) -> bool:
        """Push an envelope this node cannot run to the best compatible peer."""
        if not self.config.remote_dispatch_enable:
            return False
        dispatch_hops = int(envelope.get("dispatch_hops", 0) or 0)
        if dispatch_hops >= max(1, self.config.remote_dispatch_limit):
            return False
        kind = str(envelope.get("envelope_kind") or "task")
        required_roles = envelope.get("target_roles", []) if kind == "request" else envelope.get("required_roles", [])
        if not isinstance(required_roles, list):
            required_roles = []
        body = envelope.get("request") if kind == "request" and isinstance(envelope.get("request"), dict) else {}
        if kind != "request":
            body = envelope.get("task") if isinstance(envelope.get("task"), dict) else {}
        excluded_peer_ids = {
            optional_peer_id(value)
            for value in (envelope.get("excluded_peer_ids", []) if isinstance(envelope.get("excluded_peer_ids"), list) else [])
        }
        excluded_peer_ids.discard("")
        required_role_set = {str(role).lower() for role in required_roles}
        constraints = _peer_constraints(body, envelope)
        peer = self._select_dispatch_peer(required_role_set, excluded_peer_ids, constraints)
        if not peer:
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False
        payload = dict(envelope)
        payload["dispatch_hops"] = dispatch_hops + 1
        payload["dispatched_by"] = self.config.node_id
        payload["dispatched_utc"] = utc_now()
        payload["result_return_url"] = self.peer_network.advertised_http_base_url.rstrip("/") + "/results/dispatch"
        base_urls = self._dispatch_base_urls(peer[0])
        if not base_urls:
            self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
            return False

        path = "/requests/dispatch" if kind == "request" else "/tasks/dispatch"
        raw = stable_json(payload).encode("utf-8")
        # The accepting URL is not used further (historically unused too).
        dispatched_url = self._post_dispatch(base_urls, path, raw)
        if dispatched_url:
            self.metrics["dispatched"] = int(self.metrics.get("dispatched", 0) or 0) + 1
            item_id = str(envelope.get("request_id") or envelope.get("task_id") or "unknown")
            safe_item = safe_id(item_id)
            self.update_envelope_status(envelope, "dispatched", {"result_hash": "", "dispatched_to": peer[0].get("node_id", "")})
            append_jsonl(
                self.events_path,
                {
                    "schema_version": 1,
                    "timestamp_utc": utc_now(),
                    "node_id": self.config.node_id,
                    "kind": "dispatch",
                    "item_id": safe_item,
                    "target_peer": peer[0].get("node_id", ""),
                    "roles": required_roles,
                },
            )
            return True
        self.metrics["dispatch_failed"] = int(self.metrics.get("dispatch_failed", 0) or 0) + 1
        return False

    def _select_dispatch_peer(
        self,
        required_role_set: set[str],
        excluded_peer_ids: set[str],
        constraints: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Best peer (as a 0/1-item list), retrying while discovery converges."""
        peer: list[dict[str, Any]] = []
        for attempt in range(4):
            peer = self.peer_network.select_peers(
                required_roles=required_role_set,
                limit=1,
                exclude={self.config.node_id, *excluded_peer_ids},
                constraints=constraints,
            )
            if peer:
                break

            # Peer discovery and on-chain reputation publication are
            # asynchronous. This is especially visible for --once jobs,
            # which otherwise have no later convergence cycle to retry a
            # dispatch after the first empty peer snapshot.
            if attempt == 0:
                try:
                    self.peer_network.sync_once()
                except Exception:
                    pass
            self.refresh_known_peer_onchain_reputations(force=True)
            if attempt < 3:
                time.sleep(0.05)
        return peer

    @staticmethod
    def _dispatch_base_urls(peer: dict[str, Any]) -> list[str]:
        """Advertised URL first, then one ``http://ip:port`` per candidate."""
        base_urls = []
        primary_url = str(peer.get("http_base_url", "")).rstrip("/")
        if primary_url:
            base_urls.append(primary_url)
        for cand in peer.get("candidates", []):
            if isinstance(cand, dict) and cand.get("ip") and cand.get("port"):
                ip = str(cand["ip"])
                port = cand["port"]
                formatted_ip = f"[{ip}]" if ":" in ip else ip
                cand_url = f"http://{formatted_ip}:{port}".rstrip("/")
                if cand_url not in base_urls:
                    base_urls.append(cand_url)
        return base_urls

    def _post_dispatch(self, base_urls: list[str], path: str, raw: bytes) -> str:
        """POST to each URL in turn; return the first that accepted (200/202) or ""."""
        for base_url in base_urls:
            request = urllib.request.Request(
                base_url + path,
                data=raw,
                method="POST",
                headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    if response.status in {200, 202}:
                        return base_url
            except Exception:
                continue
        return ""

    def return_dispatched_result(self, envelope: dict[str, Any], result: dict[str, Any], log_payload: dict[str, Any]) -> None:
        """POST a result back to the node that dispatched the envelope (if any)."""
        return_url = str(envelope.get("result_return_url", "")).strip()
        origin_node_id = str(envelope.get("dispatched_by", "")).strip()
        if not return_url or not origin_node_id or origin_node_id == self.config.node_id:
            return
        item_id = str(envelope.get("request_id") or envelope.get("task_id") or "")
        if not item_id:
            return
        safe_item = safe_id(item_id)
        content_blobs = self._result_content_blobs(result)
        payload = {
            "schema_version": 1,
            "item_id": safe_item,
            "envelope_kind": str(envelope.get("envelope_kind") or "task"),
            "result": result,
            "log": log_payload,
            "handled_by": self.config.node_id,
            "status": "completed" if bool(result.get("success", True)) else "failed",
        }
        if content_blobs:
            payload["content_blobs"] = content_blobs
        raw = stable_json(payload).encode("utf-8")
        path = urlparse(return_url).path or "/results/dispatch"
        request = urllib.request.Request(
            return_url,
            data=raw,
            method="POST",
            headers=self.peer_network._signed_headers("POST", path, raw, {"Content-Type": "application/json"}),
        )
        http_status = 0
        error = ""
        return_started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                http_status = int(response.status)
                ok = http_status in {200, 202}
        except (urllib.error.URLError, OSError) as exc:
            ok = False
            error = str(exc)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "result_return",
                "item_id": safe_item,
                "target_node": origin_node_id,
                "ok": ok,
                "http_status": http_status,
                "error": error,
                "return_url": return_url,
                "duration_ms": round((time.monotonic() - return_started) * 1000),
            },
        )

    def _result_content_blobs(self, result: dict[str, Any]) -> list[dict[str, str]]:
        """Inline (base64) the output/proof artefacts, at most 16 MiB each.

        A NATed worker can POST its result to the scheduler but cannot in
        general accept a later inbound HTTP fetch of its P2P content. Attach
        bounded result artifacts to that already-authenticated return so the
        scheduler becomes a durable, reachable content source.
        """
        content_blobs: list[dict[str, str]] = []
        seen_content: set[str] = set()
        for ref_name in ("output_ref", "proof_ref"):
            ref = result.get(ref_name)
            if not isinstance(ref, dict):
                continue
            candidates = [ref]
            shared_ref = ref.get("shared_ref")
            if isinstance(shared_ref, dict):
                candidates.append(shared_ref)
            for candidate in candidates:
                content_id = str(candidate.get("content_id", "")).strip()
                if content_id in seen_content or len(content_id) != 64 or any(char not in "0123456789abcdef" for char in content_id.lower()):
                    continue
                content_path = self.config.export_dir / "p2p" / content_id
                try:
                    content = content_path.read_bytes()
                except OSError:
                    continue
                if len(content) > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != content_id:
                    continue
                content_blobs.append({"content_id": content_id, "data_b64": base64.b64encode(content).decode("ascii")})
                seen_content.add(content_id)
                break
        return content_blobs

    def ingest_content_blobs(self, payload: dict[str, Any]) -> list[str]:
        """Store the inline ``content_blobs`` of a payload in the local p2p store."""
        return ingest_content_blobs(self.config.export_dir, payload)

    def ingest_dispatched_result(self, payload: dict[str, Any]) -> None:
        """Persist a result returned by a remote worker and forward it upstream."""
        item_id = safe_id(str(payload.get("item_id", "")))
        if not item_id:
            raise ValueError("missing_item_id")
        path_item = safe_path_id(item_id)
        result = payload.get("result")
        log_payload = payload.get("log")
        if not isinstance(result, dict) or not isinstance(log_payload, dict):
            raise ValueError("missing_result_payload")
        self.ingest_content_blobs(payload)
        kind = str(payload.get("envelope_kind") or "task")
        atomic_write_json(self.config.export_dir / f"result.{path_item}.json", result)
        atomic_write_json(self.config.export_dir / f"logs.{path_item}.json", log_payload)
        target_dir = self.config.export_dir / ("requests" if kind == "request" else "tasks")
        envelope_path = target_dir / f"{path_item}.json"
        current = read_json(envelope_path, {})
        if not isinstance(current, dict):
            current = {}
        current["status"] = str(payload.get("status", "completed"))
        current["handled_by"] = str(payload.get("handled_by", result.get("node_id", "")))
        current["handled_utc"] = utc_now()
        current["result_hash"] = result.get("result_hash") or result.get("input_hash", "")
        current["result_resource"] = f"resources://silicium/results/by-task/{item_id}"
        for key in ("error", "error_type", "traceback"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                current[key] = value
        atomic_write_json(envelope_path, current)
        try:
            append_jsonl(
                self.config.export_dir / "rpc.events.ndjson",
                {
                    "schema_version": 1,
                    "event": f"task.{current['status']}",
                    "item_id": item_id,
                    "timestamp_utc": utc_now(),
                    "handled_by": current.get("handled_by", ""),
                    "duration_ms": result.get("duration_ms", 0),
                    "performance": result.get("performance", {}),
                },
            )
        except Exception:
            pass
        self.return_dispatched_result(current, result, log_payload)
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "result_ingest",
                "item_id": item_id,
                "source_node": str(payload.get("handled_by", result.get("node_id", ""))),
            },
        )
