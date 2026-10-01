"""Content-addressed transfers between peers: fetch (HTTP, ICE, relay) and replicate."""

from __future__ import annotations

import ipaddress
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlparse

from tools.node.util import safe_id, sha256_bytes


class ContentMixin:
    """Move content-addressed blobs between peers."""

    def fetch_content(self, content_id: str, preferred_peer_id: str = "") -> tuple[bytes, dict[str, Any]]:
        """Fetch a blob: public HTTP, ICE, HTTP, UDP punch then relays."""
        peers = self.peers_snapshot().get("peers", [])
        candidates = []
        if preferred_peer_id:
            candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) == preferred_peer_id])
        candidates.extend([peer for peer in peers if str(peer.get("node_id", "")) != preferred_peer_id])
        for peer in candidates:
            ice_capable = bool(self.config.nat_punch_enable and "ice_v1" in {
                str(feature) for feature in (peer.get("features", []) if isinstance(peer.get("features", []), list) else [])
            })
            if self._prefer_peer_http(peer) and not ice_capable:
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
            ice_result = self._fetch_direct_ice(peer, content_id)
            if ice_result is not None:
                return ice_result
            if self._prefer_peer_http(peer):
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
        if preferred_peer_id:
            self.request_udp_punch(preferred_peer_id)
            time.sleep(0.1)
            for peer in candidates:
                if str(peer.get("node_id", "")) != preferred_peer_id:
                    continue
                data = self._fetch_direct_from_peer(peer, content_id)
                if data is not None:
                    return data, self._attested_fetch_meta(
                        peer,
                        content_id=content_id,
                        data=data,
                        route="direct",
                        transport_backend="peer-http-after-punch",
                        endpoint=str(peer.get("http_base_url", "")),
                    )
        relayed = self._fetch_via_relays(content_id, preferred_peer_id, candidates)
        if relayed is not None:
            return relayed
        raise FileNotFoundError(f"peer_content_not_found:{content_id}")

    @staticmethod
    def _prefer_peer_http(peer: Mapping[str, Any]) -> bool:
        """Use reachable public HTTP before paying the ICE setup cost."""
        parsed = urlparse(str(peer.get("http_base_url", "")).strip())
        if parsed.scheme.lower() == "https" and parsed.hostname:
            return True
        try:
            address = ipaddress.ip_address(str(parsed.hostname or ""))
        except ValueError:
            return False
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_reserved
        )

    def _attested_fetch_meta(
        self,
        peer: Mapping[str, Any],
        *,
        content_id: str,
        data: bytes,
        route: str,
        transport_backend: str,
        endpoint: str = "",
        relay_peer_id: str = "",
    ) -> dict[str, Any]:
        meta = dict(peer)
        meta["transport_route"] = route
        meta["transport_backend"] = transport_backend
        meta["path_attestation"] = self.record_transport_attestation(
            route=route,
            transport_backend=transport_backend,
            remote_peer_id=str(peer.get("node_id", "")),
            proof_scope="payload_transfer",
            content_id=content_id,
            content_sha256=sha256_bytes(data),
            size_bytes=len(data),
            endpoint=endpoint,
            relay_peer_id=relay_peer_id,
            success=True,
        )
        return meta

    def _fetch_direct_ice(self, peer: dict[str, Any], content_id: str) -> tuple[bytes, dict[str, Any]] | None:
        if not self.config.nat_punch_enable or self.direct_transport.name != "ice":
            return None
        features = peer.get("features", []) if isinstance(peer.get("features", []), list) else []
        if "ice_v1" not in {str(feature) for feature in features}:
            return None
        peer_id = safe_id(str(peer.get("node_id", "")))
        if not peer_id or peer_id == self.node_id:
            return None
        session_id = self._ice_content_sessions.get(peer_id, "")
        if session_id:
            result = self.direct_transport.request_content(session_id, content_id)
            if result is not None:
                return result
            self._ice_content_sessions.pop(peer_id, None)
        session_id = self._open_ice_content_session(peer, content_id)
        if not session_id:
            return None
        result = self.direct_transport.request_content(session_id, content_id)
        if result is None:
            self._ice_content_sessions.pop(peer_id, None)
            return None
        self._ice_content_sessions[peer_id] = session_id
        return result

    def _fetch_direct_from_peer(self, peer: dict[str, Any], content_id: str) -> bytes | None:
        base_url = str(peer.get("http_base_url", "")).rstrip("/")
        if not base_url:
            return None
        path = f"/p2p/{quote(content_id, safe='')}"
        request = urllib.request.Request(base_url + path, headers=self._signed_headers("GET", path, b""))
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.read()
        except urllib.error.URLError:
            return None

    def _fetch_via_relays(self, content_id: str, preferred_peer_id: str, candidates: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]] | None:
        target_peer_id = preferred_peer_id or str(next((peer.get("node_id", "") for peer in candidates if peer.get("node_id")), ""))
        if not target_peer_id:
            return None
        relays = self.select_peers(required_roles=set(), limit=max(1, self.config.relay_hops), require_relay=True, exclude={target_peer_id})
        if not relays:
            relays = [peer for peer in candidates if str(peer.get("node_id", "")) != target_peer_id and bool(peer.get("relay_capable", False))]
        for relay in relays:
            relay_url = str(relay.get("http_base_url", "")).rstrip("/")
            if not relay_url:
                continue
            path = f"/relay/fetch?peer_id={quote(target_peer_id, safe='')}&content_id={quote(content_id, safe='')}"
            request = urllib.request.Request(relay_url + path, headers=self._signed_headers("GET", path, b""))
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        data = response.read()
                        peer = {
                            "node_id": target_peer_id,
                            "http_base_url": relay_url,
                            "relayed_via": relay.get("node_id", ""),
                        }
                        return data, self._attested_fetch_meta(
                            peer,
                            content_id=content_id,
                            data=data,
                            route="relay",
                            transport_backend="relay-http",
                            endpoint=relay_url,
                            relay_peer_id=str(relay.get("node_id", "")),
                        )
                except (urllib.error.URLError, TimeoutError, OSError):
                    if attempt < 2:
                        time.sleep(0.05)
        return None

    def replicate_content(
        self,
        content_id: str,
        data: bytes,
        *,
        target_factor: int,
        required_quorum: int,
        required_roles: Iterable[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Push a blob to up to ``target_factor`` storage peers; report the quorum."""
        peers = self.select_peers(
            required_roles=set(required_roles or {"storage"}),
            limit=max(0, target_factor),
            exclude={self.node_id},
            constraints=constraints,
        )
        report = {"attempted": 0, "stored": 0, "quorum": max(0, required_quorum), "satisfied": True, "peers": []}
        for peer in peers:
            report["attempted"] += 1
            ok = self._push_replica(peer, content_id, data)
            report["peers"].append({"node_id": peer.get("node_id", ""), "ok": ok})
            if ok:
                report["stored"] += 1
        report["satisfied"] = report["stored"] >= max(0, required_quorum)
        if report["stored"] > 0:
            self.publish("content_replicated", {"content_id": content_id, "stored": report["stored"], "quorum": report["quorum"]})
        return report

    def _push_replica(self, peer: dict[str, Any], content_id: str, data: bytes) -> bool:
        base_url = str(peer.get("http_base_url", "")).rstrip("/")
        if not base_url:
            return False
        path = f"/p2p/ingest?content_id={quote(content_id, safe='')}"
        request = urllib.request.Request(
            base_url + path,
            data=data,
            method="POST",
            headers=self._signed_headers("POST", path, data, {"Content-Type": "application/octet-stream"}),
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except urllib.error.URLError:
            return False

    def _serve_direct_content(self, session_id: str, requester_peer_id: str, content_id: str) -> tuple[bool, bytes, str]:
        requester_id = safe_id(requester_peer_id)
        with self._lock:
            session = dict(self._direct_sessions.get(str(session_id), {}))
        if str(session.get("status", "")) != "direct" or safe_id(str(session.get("remote_peer_id", ""))) != requester_id:
            return False, b"", "session_not_direct"
        if not content_id or Path(content_id).name != content_id:
            return False, b"", "content_id_invalid"
        content_path = self.export_dir / "p2p" / content_id
        try:
            if not content_path.is_file():
                return False, b"", "content_not_found"
            return True, content_path.read_bytes(), ""
        except OSError:
            return False, b"", "content_read_failed"
