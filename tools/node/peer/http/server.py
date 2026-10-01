"""Bounded threading HTTP server of a peer and the mixin that starts it."""

from __future__ import annotations

import http.server
import socketserver
import threading
from typing import Any

from tools.node.peer.http.handler import make_handler_class


class BoundedThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Threading HTTP server with a bounded number of in-flight requests."""

    daemon_threads = True
    block_on_close = False

    def __init__(self, *args: Any, max_workers: int, **kwargs: Any) -> None:
        worker_limit = max(1, min(256, int(max_workers)))
        # The default TCP listen backlog is five on many Linux
        # systems. That is enough for a single desktop node but
        # drops synchronized claim/heartbeat bursts before the
        # bounded handler pool can accept them.
        self.request_queue_size = max(64, min(1024, worker_limit * 4))
        self._request_slots = threading.BoundedSemaphore(worker_limit)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        # Reject excess work quickly; peer callers already retry and
        # this keeps the accept loop and process thread count bounded.
        if not self._request_slots.acquire(timeout=0.25):
            self.close_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            self.close_request(request)

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class HttpServerMixin:
    """Start the peer HTTP server and derive the advertised base URLs."""

    def _start_http_server(self) -> None:
        server = BoundedThreadingHTTPServer(
            (self.config.peer_http_bind, self.config.peer_http_port),
            make_handler_class(self),
            max_workers=self.config.peer_http_max_workers,
        )
        self._http_server = server
        bind_host, bind_port = server.server_address[:2]
        local_host = "127.0.0.1" if bind_host in {"0.0.0.0", ""} else str(bind_host)
        self.http_base_url = f"http://{local_host}:{bind_port}"
        self.advertised_http_base_url = (
            self.config.peer_advertise_url.strip().rstrip("/")
            or f"http://{self._advertised_http_host()}:{self._advertised_http_port()}"
        )
        self.mesh_post_url = self.advertised_http_base_url.rstrip("/") + "/mesh"

        self._http_thread = threading.Thread(target=server.serve_forever, name=f"silicium-peer-http-{self.node_id}", daemon=True)
        self._http_thread.start()
