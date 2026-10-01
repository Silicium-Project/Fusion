"""Advertised HTTP/gossip addresses and target parsing helpers."""

from __future__ import annotations

from urllib.parse import urlparse


class AddressingMixin:
    """Resolve the addresses this node advertises and parse peer targets."""

    def _advertised_http_host(self) -> str:
        return str(self.config.peer_advertise_host or "").strip() or urlparse(self.http_base_url).hostname or "127.0.0.1"

    def _advertised_http_port(self) -> int:
        if self.config.peer_advertise_port > 0:
            return int(self.config.peer_advertise_port)
        parsed = urlparse(self.http_base_url)
        return int(parsed.port or 0)

    def _advertised_gossip_host(self) -> str:
        return str(self.config.gossip_advertise_host or "").strip() or str(self.config.gossip_bind)

    def _advertised_gossip_port(self) -> int:
        if self.config.gossip_advertise_port > 0:
            return int(self.config.gossip_advertise_port)
        if self.config.gossip_port > 0:
            return int(self.config.gossip_port)
        if self.config.peer_advertise_port > 0:
            return int(self.config.peer_advertise_port)
        if self.config.peer_http_port > 0:
            return int(self.config.peer_http_port)
        return 46101

    def _normalize_http_target(self, target: str) -> str:
        value = str(target or "").strip()
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            path = parsed.path.rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{path}"
        return ""

    def _parse_udp_target(self, target: str) -> tuple[str, int]:
        value = str(target or "").strip()
        if not value:
            return "", 0
        if value.startswith("udp://"):
            value = value[len("udp://") :]
        if "://" in value:
            return "", 0
        host, _, port_raw = value.partition(":")
        try:
            port = int(port_raw)
        except ValueError:
            return "", 0
        return host.strip(), port
