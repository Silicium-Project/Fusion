"""Request handler of the peer HTTP server and its ordered route tables.

The handler class is created per ``PeerNetwork`` by :func:`make_handler_class`
so that the route functions can reach the owning instance. Routes are matched
in the exact order of the original monolithic handler: the first matching
entry answers, so exact paths that share a prefix with a catch-all prefix
(``/p2p/sessions`` vs ``/p2p/``) must stay listed before it.
"""

from __future__ import annotations

import http.server
import ipaddress
from typing import TYPE_CHECKING, Any, Callable

from tools.node.peer.http.common import JSON_CONTENT_TYPE
from tools.node.peer.http import (
    routes_discovery,
    routes_mesh,
    routes_p2p,
    routes_relay,
    routes_status,
    routes_tasks,
    routes_updates,
)

if TYPE_CHECKING:  # annotations only; avoids an import cycle
    from tools.node.peer import PeerNetwork

def _exact(path: str) -> Callable[[str], bool]:
    return lambda candidate: candidate == path


def _one_of(*paths: str) -> Callable[[str], bool]:
    allowed = set(paths)
    return lambda candidate: candidate in allowed


def _prefix(prefix: str) -> Callable[[str], bool]:
    return lambda candidate: candidate.startswith(prefix)


# (matcher on the raw request path, route function). Order is significant.
GET_ROUTES: tuple[tuple[Callable[[str], bool], Callable[..., None]], ...] = (
    (_one_of("/health", "/healthz"), routes_status.get_health),
    (_exact("/peers"), routes_status.get_peers),
    (_exact("/discovery/snapshot"), routes_discovery.get_snapshot),
    (_exact("/discovery/observe"), routes_discovery.get_observe),
    (_prefix("/events/recent"), routes_status.get_recent_events),
    (_prefix("/events/task-controls"), routes_status.get_task_controls),
    (_exact("/p2p/sessions"), routes_p2p.get_sessions),
    (_exact("/updates/manifest"), routes_updates.get_manifest),
    (_prefix("/updates/content/"), routes_updates.get_content),
    (_exact("/p2p/sessions/pending"), routes_p2p.get_pending_sessions),
    (_exact("/p2p/transport"), routes_p2p.get_transport),
    (_exact("/p2p/attestations"), routes_p2p.get_attestations),
    (_prefix("/p2p/"), routes_p2p.get_content),
    (_prefix("/relay/fetch"), routes_relay.get_fetch),
)

# POST routes after the shared signature check (``/updates/cache/`` is handled
# before it, see ``do_POST``). Route functions receive the raw request body.
POST_ROUTES: tuple[tuple[Callable[[str], bool], Callable[..., None]], ...] = (
    (_exact("/mesh"), routes_mesh.post_mesh),
    (_exact("/gossip/publish"), routes_mesh.post_gossip_publish),
    (_exact("/discovery/register"), routes_discovery.post_register),
    (_exact("/p2p/peers/register"), routes_discovery.post_peer_register),
    (_exact("/p2p/candidates"), routes_discovery.post_candidates),
    (_exact("/p2p/sessions/request"), routes_p2p.post_session_request),
    (_prefix("/p2p/sessions/"), routes_p2p.post_session_action),
    (_prefix("/p2p/ingest"), routes_p2p.post_ingest),
    (_exact("/tasks/claim"), routes_tasks.post_claim),
    (_exact("/tasks/dispatch"), routes_tasks.post_task_dispatch),
    (_exact("/requests/dispatch"), routes_tasks.post_request_dispatch),
    (_exact("/results/dispatch"), routes_tasks.post_result_dispatch),
    (_prefix("/relay/mesh"), routes_relay.post_mesh),
    (_exact("/relay/punch"), routes_relay.post_punch),
)


class PeerRequestHandler(http.server.BaseHTTPRequestHandler):
    """Dispatch peer HTTP requests to the route functions of ``peer_network``."""

    # Set on the per-network subclass built by make_handler_class().
    peer_network: Any = None

    def _local_or_authorized(self, body: bytes = b"") -> bool:
        """Accept loopback callers (host-side probes) or signed peer requests."""
        try:
            if ipaddress.ip_address(str(self.client_address[0])).is_loopback:
                return True
        except ValueError:
            pass
        return self.peer_network._authorize_peer_request(self, body)

    def signed_by_peer(self, body: bytes = b"") -> bool:
        """Return whether the request carries a valid signed peer identity."""
        return self.peer_network._authorize_peer_request(self, body)

    def send_body(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str = JSON_CONTENT_TYPE,
        cache_control: str | None = None,
    ) -> None:
        """Write a complete response (headers in the historical order)."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        for matches, route in GET_ROUTES:
            if matches(self.path):
                route(self, self.peer_network)
                return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            size = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            size = 0
        raw = self.rfile.read(max(0, size))
        if self.path.startswith("/updates/cache/") and self._local_or_authorized(raw):
            routes_updates.post_cache(self, self.peer_network, raw)
            return
        # The VPS e2e probe runs on the host and uses loopback. Keep
        # that local control path available while requiring signed
        # requests from every non-loopback caller.
        if not self._local_or_authorized(raw):
            self.send_error(403)
            return
        for matches, route in POST_ROUTES:
            if matches(self.path):
                route(self, self.peer_network, raw)
                return
        self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def make_handler_class(peer_network: PeerNetwork) -> type[PeerRequestHandler]:
    """Build a handler class bound to ``peer_network`` (one per HTTP server)."""
    return type("_PeerHandler", (PeerRequestHandler,), {"peer_network": peer_network})
