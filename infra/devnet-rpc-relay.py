#!/usr/bin/env python3
"""Small, private Solana Devnet JSON-RPC relay for the VPS worker bridge."""

from __future__ import annotations

import ipaddress
import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


UPSTREAM = os.environ.get("SILICIUM_DEVNET_RPC_UPSTREAM", "https://api.devnet.solana.com")
LISTEN_HOST = os.environ.get("SILICIUM_DEVNET_RPC_BIND", "172.23.0.1")
LISTEN_PORT = int(os.environ.get("SILICIUM_DEVNET_RPC_PORT", "8899"))
ALLOWED_CIDRS = tuple(
    ipaddress.ip_network(value.strip())
    for value in os.environ.get("SILICIUM_DEVNET_RPC_ALLOWED_CIDRS", "172.23.0.0/24").split(",")
    if value.strip()
)
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
RETRYABLE_STATUS = {429, 502, 503, 504}
UPSTREAM_SLOTS = threading.BoundedSemaphore(2)
UPSTREAM_PACE_LOCK = threading.Lock()
UPSTREAM_MIN_INTERVAL = 0.2
NEXT_UPSTREAM_START = 0.0
UPSTREAM_BACKOFF_UNTIL = 0.0

upstream = urlsplit(UPSTREAM)
if upstream.scheme != "https" or not upstream.hostname or "devnet" not in upstream.hostname.lower():
    raise SystemExit("RPC relay requires an HTTPS Devnet upstream.")
if not ALLOWED_CIDRS or any(network.version != 4 for network in ALLOWED_CIDRS):
    raise SystemExit("RPC relay requires at least one IPv4 allowlist network.")
if ipaddress.ip_address(LISTEN_HOST) not in {network.network_address + 1 for network in ALLOWED_CIDRS}:
    raise SystemExit("RPC relay bind address must be the worker bridge gateway.")


def retry_delay(headers, attempt: int) -> float:
    advertised = headers.get("Retry-After") if headers else None
    if advertised:
        try:
            return min(12.0, max(0.0, float(advertised)))
        except ValueError:
            pass
    return min(8.0, 0.5 * (2**attempt)) + random.random() * 0.25


def is_json_rpc_rate_limit(payload: bytes) -> bool:
    try:
        body = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    error = body.get("error") if isinstance(body, dict) else None
    return isinstance(error, dict) and error.get("code") == 429


def pace_upstream_request() -> None:
    global NEXT_UPSTREAM_START
    while True:
        with UPSTREAM_PACE_LOCK:
            now = time.monotonic()
            wait_until = max(NEXT_UPSTREAM_START, UPSTREAM_BACKOFF_UNTIL)
            if wait_until <= now:
                NEXT_UPSTREAM_START = now + UPSTREAM_MIN_INTERVAL
                return
        time.sleep(wait_until - now)


def back_off_upstream(delay: float) -> None:
    global UPSTREAM_BACKOFF_UNTIL
    with UPSTREAM_PACE_LOCK:
        UPSTREAM_BACKOFF_UNTIL = max(UPSTREAM_BACKOFF_UNTIL, time.monotonic() + delay)


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "SiliciumDevnetRelay/1"
    sys_version = ""

    def _allowed(self) -> bool:
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return address in ipaddress.ip_network("127.0.0.0/8") or any(
            address in network for network in ALLOWED_CIDRS
        )

    def _respond(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(200, b'{"status":"ok","cluster":"devnet"}')
            return
        self._respond(404, b'{"error":"not found"}')

    def do_POST(self) -> None:
        if not self._allowed():
            self._respond(403, b'{"error":"forbidden"}')
            return
        if self.path not in {"/devnet", "/devnet/"}:
            self._respond(404, b'{"error":"not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 1 or length > MAX_REQUEST_BYTES:
            self._respond(413, b'{"error":"invalid request size"}')
            return
        if "application/json" not in self.headers.get("Content-Type", "").lower():
            self._respond(415, b'{"error":"application/json required"}')
            return
        payload = self.rfile.read(length)
        try:
            request_json = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(400, b'{"error":"invalid JSON"}')
            return
        if not isinstance(request_json, (dict, list)):
            self._respond(400, b'{"error":"invalid JSON-RPC request"}')
            return

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        request = Request(UPSTREAM, data=payload, headers=headers, method="POST")
        for attempt in range(4):
            status = 502
            response_headers = None
            try:
                with UPSTREAM_SLOTS:
                    pace_upstream_request()
                    with urlopen(request, timeout=25) as response:
                        status = response.status
                        response_headers = response.headers
                        body = response.read(MAX_RESPONSE_BYTES + 1)
            except HTTPError as error:
                status = error.code
                response_headers = error.headers
                body = error.read(MAX_RESPONSE_BYTES + 1)
            except (TimeoutError, URLError, OSError):
                body = b'{"error":{"code":-32000,"message":"Devnet RPC upstream unavailable"}}'
            if len(body) > MAX_RESPONSE_BYTES:
                self._respond(502, b'{"error":"upstream response too large"}')
                return
            should_retry = status in RETRYABLE_STATUS or (status == 200 and is_json_rpc_rate_limit(body))
            if not should_retry:
                content_type = "application/json"
                if response_headers:
                    content_type = response_headers.get("Content-Type", content_type)
                self._respond(status, body, content_type)
                return
            delay = retry_delay(response_headers, attempt)
            back_off_upstream(delay)
            if attempt == 3:
                content_type = "application/json"
                if response_headers:
                    content_type = response_headers.get("Content-Type", content_type)
                self._respond(status, body, content_type)
                return

    def log_message(self, _format: str, *_args) -> None:
        return


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64


server = RelayServer((LISTEN_HOST, LISTEN_PORT), RelayHandler)
server.serve_forever(poll_interval=0.5)
