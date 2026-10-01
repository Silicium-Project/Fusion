"""NAT traversal candidates: gather host/server-reflexive addresses and normalise peers'."""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from tools.node.util import (
    atomic_write_json,
    safe_id,
    sha256_bytes,
    stable_json,
    utc_now,
)


class CandidatesMixin:
    """Gather, normalise and expire UDP connectivity candidates."""

    def local_candidates_snapshot(self) -> list[dict[str, Any]]:
        """Unexpired local candidates (also persisted)."""
        now = int(time.time())
        with self._lock:
            self._local_candidates = [candidate for candidate in self._local_candidates if int(candidate.get("expires_unix", 0) or 0) > now]
            candidates = [dict(candidate) for candidate in self._local_candidates]
        self._write_candidate_snapshot(candidates)
        return candidates

    def candidate_diagnostics(self) -> dict[str, Any]:
        """Summary of candidates, NAT behaviour and transport backend."""
        candidates = self.local_candidates_snapshot()
        selected = self._select_candidate(candidates)
        return {
            "candidate_count": len(candidates),
            "candidate_types": sorted({str(candidate.get("candidate_type", "")) for candidate in candidates if candidate.get("candidate_type")}),
            "selected_candidate": selected,
            "observed_public_address": self._observed_public_address,
            "nat_behavior": self._nat_behavior,
            "direct_transport_backend": self.direct_transport.name,
            "direct_transport_features": self.direct_transport.features(),
        }

    def refresh_candidates(self, *, force: bool = False) -> list[dict[str, Any]]:
        """Re-gather candidates unless fresh ones exist (``force`` to always refresh)."""
        now = int(time.time())
        refresh_s = max(1, int(self.config.p2p_candidate_refresh_s))
        with self._lock:
            fresh = any(int(candidate.get("expires_unix", 0) or 0) > now for candidate in self._local_candidates)
            recently_refreshed = (now - self._last_candidate_refresh_unix) < refresh_s
        if not force and fresh and recently_refreshed:
            return self.local_candidates_snapshot()
        gathered = self._gather_host_candidates(now)
        gathered.extend(self._discover_server_reflexive_candidates(now))
        candidates = self._merge_candidate_list(gathered, self.node_id, now)
        with self._lock:
            self._local_candidates = candidates
            self._last_candidate_refresh_unix = float(now)
        self._write_candidate_snapshot(candidates)
        return [dict(candidate) for candidate in candidates]

    def record_observed_candidate(self, observed_ip: str, *, source: str = "server-observed", observed_port: int = 0) -> dict[str, Any] | None:
        """Add a server-reflexive candidate seen by another node."""
        now = int(time.time())
        candidate = self._server_reflexive_candidate(observed_ip, now, source=source, observed_port=observed_port)
        if candidate is None:
            return None
        with self._lock:
            merged = self._merge_candidate_list([*self._local_candidates, candidate], self.node_id, now)
            self._local_candidates = merged
            self._last_candidate_refresh_unix = float(now)
        self._write_candidate_snapshot(self.local_candidates_snapshot())
        self._record_self_peer()
        return dict(candidate)

    def _write_candidate_snapshot(self, candidates: list[dict[str, Any]]) -> None:
        atomic_write_json(
            self.candidates_path,
            {
                "schema_version": 1,
                "node_id": self.node_id,
                "updated_utc": utc_now(),
                "observed_public_address": self._observed_public_address,
                "nat_behavior": self._nat_behavior,
                "selected_candidate": self._select_candidate(candidates),
                "candidates": candidates,
            },
        )

    def _select_candidate(self, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not candidates:
            return None
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                1 if bool(candidate.get("internet_routable", False)) else 0,
                1 if str(candidate.get("candidate_type", "")) == "srflx" else 0,
                int(candidate.get("priority", 0) or 0),
            ),
            reverse=True,
        )
        return dict(ranked[0]) if ranked else None

    def _gather_host_candidates(self, now: int) -> list[dict[str, Any]]:
        port = self._advertised_gossip_port()
        if port <= 0:
            return []
        hosts: list[tuple[str, str]] = [
            (self._advertised_gossip_host(), "advertised-gossip"),
            (str(self.config.gossip_bind), "gossip-bind"),
        ]
        default_route = self._default_route_ip()
        if default_route:
            hosts.append((default_route, "default-route"))
        try:
            hosts.append((socket.gethostname(), "hostname"))
        except Exception:
            pass
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for host, source in hosts:
            for ip in self._resolve_candidate_addresses(host):
                if ip in seen:
                    continue
                seen.add(ip)
                candidates.append(self._make_candidate("host", ip, port, source, 100, now))
        return candidates

    def _discover_server_reflexive_candidates(self, now: int) -> list[dict[str, Any]]:
        targets = {self._normalize_http_target(seed) for seed in self.config.discovery_seeds + self.config.seed_peers}
        targets.update(self._sync_targets())
        targets.discard("")
        targets.discard(self.advertised_http_base_url)
        candidates: list[dict[str, Any]] = []
        for base_url in sorted(target for target in targets if target):
            path = "/discovery/observe"
            request = urllib.request.Request(base_url.rstrip("/") + path, headers=self._signed_headers("GET", path, b""))
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            candidate = self._server_reflexive_candidate(
                str(payload.get("observed_ip", "")),
                now,
                source=f"observe:{base_url.rstrip('/')}",
                observed_port=0,
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _server_reflexive_candidate(self, observed_ip: str, now: int, *, source: str, observed_port: int = 0) -> dict[str, Any] | None:
        port = int(observed_port or 0) or self._advertised_gossip_port()
        if port <= 0:
            return None
        candidate = self._make_candidate("srflx", observed_ip, port, source, 900, now)
        normalized = self._normalize_candidate(candidate, self.node_id, now)
        if normalized is None:
            return None
        if bool(normalized.get("internet_routable", False)):
            self._observed_public_address = str(normalized.get("ip", ""))
            self._nat_behavior = "public_or_endpoint_independent" if self._has_matching_public_host(normalized) else "address_translated"
        else:
            self._nat_behavior = "private_or_unroutable_observed"
        return normalized

    def _make_candidate(self, candidate_type: str, ip: str, port: int, source: str, priority: int, now: int) -> dict[str, Any]:
        ttl_s = max(1, int(self.config.p2p_candidate_ttl_s))
        return {
            "candidate_type": candidate_type,
            "transport": "udp",
            "ip": str(ip).strip(),
            "port": int(port),
            "priority": int(priority),
            "observed_unix": now,
            "expires_unix": now + ttl_s,
            "source": str(source),
        }

    def _normalize_candidate_list(self, candidates: Any, peer_id: str, now: int | None = None) -> list[dict[str, Any]]:
        if not isinstance(candidates, list):
            return []
        return self._merge_candidate_list(candidates, peer_id, int(now if now is not None else time.time()))

    def _merge_candidate_list(self, candidates: list[dict[str, Any]], peer_id: str, now: int) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        for candidate in candidates:
            normalized = self._normalize_candidate(candidate, peer_id, now)
            if normalized is None:
                continue
            key = (
                str(normalized.get("candidate_type", "")),
                str(normalized.get("transport", "")),
                str(normalized.get("ip", "")),
                int(normalized.get("port", 0) or 0),
            )
            previous = merged.get(key)
            if previous is None or int(normalized.get("priority", 0) or 0) >= int(previous.get("priority", 0) or 0):
                merged[key] = normalized
        return sorted(merged.values(), key=lambda candidate: str(candidate.get("candidate_id", "")))

    def _normalize_candidate(self, candidate: Any, peer_id: str, now: int) -> dict[str, Any] | None:
        if not isinstance(candidate, Mapping):
            return None
        candidate_type = str(candidate.get("candidate_type", "")).strip().lower()
        if candidate_type not in {"host", "srflx", "relay"}:
            return None
        transport = str(candidate.get("transport", "udp")).strip().lower()
        if transport != "udp":
            return None
        try:
            ip_value = ipaddress.ip_address(str(candidate.get("ip", "")).strip().strip("[]"))
            port = int(candidate.get("port", 0) or 0)
            if "observed_unix" in candidate:
                observed_unix = int(candidate.get("observed_unix", 0) or 0)
            else:
                observed_unix = int(int(candidate.get("observed_unix_ms", now * 1000) or 0) // 1000)
            if "expires_unix" in candidate:
                expires_unix = int(candidate.get("expires_unix", 0) or 0)
            else:
                expires_unix = int(int(candidate.get("expires_unix_ms", 0) or 0) // 1000)
            priority = int(candidate.get("priority", 0) or 0)
        except (TypeError, ValueError):
            return None
        if port <= 0 or port > 65535 or observed_unix <= 0 or expires_unix <= now:
            return None
        family = "ipv6" if ip_value.version == 6 else "ipv4"
        metadata = self._ip_metadata(ip_value)
        normalized = {
            "candidate_id": safe_id(str(candidate.get("candidate_id", "")))
            if str(candidate.get("candidate_id", "")).strip()
            else self._candidate_id(peer_id, candidate_type, transport, ip_value.compressed, port),
            "peer_id": safe_id(peer_id),
            "address_family": family,
            "transport": transport,
            "ip": ip_value.compressed,
            "port": port,
            "candidate_type": candidate_type,
            "priority": priority,
            "observed_unix": observed_unix,
            "expires_unix": expires_unix,
            "source": str(candidate.get("source", candidate.get("source_interface", ""))).strip(),
            "private": bool(metadata["private"]),
            "local": bool(metadata["local"]),
            "internet_routable": bool(metadata["public"]),
        }
        if "nat_behavior" in candidate:
            normalized["nat_behavior"] = str(candidate.get("nat_behavior", "")).strip()
        return normalized

    def _candidate_id(self, peer_id: str, candidate_type: str, transport: str, ip: str, port: int) -> str:
        digest = sha256_bytes(stable_json([safe_id(peer_id), candidate_type, transport, ip, int(port)]).encode("utf-8"))[:16]
        return f"cand-{safe_id(peer_id)}-{candidate_type}-{digest}"

    def _ip_metadata(self, ip_value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict[str, bool]:
        local = bool(ip_value.is_loopback or ip_value.is_link_local or ip_value.is_private or ip_value.is_unspecified)
        public = not bool(
            ip_value.is_loopback
            or ip_value.is_link_local
            or ip_value.is_private
            or ip_value.is_multicast
            or ip_value.is_reserved
            or ip_value.is_unspecified
        )
        return {"local": local, "private": not public, "public": public}

    def _resolve_candidate_addresses(self, host: str) -> list[str]:
        value = str(host or "").strip().strip("[]")
        if not value or value in {"0.0.0.0", "::"}:
            return []
        try:
            return [ipaddress.ip_address(value).compressed]
        except ValueError:
            pass
        addresses: set[str] = set()
        try:
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(value, None):
                if family not in {socket.AF_INET, socket.AF_INET6}:
                    continue
                addresses.add(ipaddress.ip_address(str(sockaddr[0])).compressed)
        except OSError:
            return []
        return sorted(addresses)

    def _default_route_ip(self) -> str:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(("8.8.8.8", 80))
                return str(sock.getsockname()[0])
            finally:
                sock.close()
        except OSError:
            return ""

    def _has_matching_public_host(self, observed: Mapping[str, Any]) -> bool:
        observed_ip = str(observed.get("ip", ""))
        for candidate in self._local_candidates:
            if str(candidate.get("candidate_type", "")) == "host" and bool(candidate.get("internet_routable", False)) and str(candidate.get("ip", "")) == observed_ip:
                return True
        return False

    def _prune_expired_peer_candidates(self) -> None:
        now = int(time.time())
        changed = False
        with self._lock:
            for peer in self._peers.values():
                candidates = peer.get("candidates")
                if not isinstance(candidates, list):
                    continue
                fresh = [candidate for candidate in candidates if isinstance(candidate, dict) and int(candidate.get("expires_unix", 0) or 0) > now]
                if len(fresh) != len(candidates):
                    peer["candidates"] = fresh
                    changed = True
        if changed:
            atomic_write_json(self.peers_path, {"schema_version": 1, "node_id": self.node_id, "count": len(self._peers), "peers": list(self._peers.values()), "updated_utc": utc_now()})
