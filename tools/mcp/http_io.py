"""Low-level HTTP request/response helpers for ``BaseHTTPRequestHandler``."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from typing import Any, Mapping

from .constants import JSON_CONTENT_TYPE, MAX_ENVELOPE_BYTES
from .persistence import compact_json


def send_body(handler: BaseHTTPRequestHandler, status: int, content_type: str, raw: bytes) -> None:
    """Send a complete response with an explicit Content-Length."""
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    """Serialise ``payload`` and send it as a JSON response."""
    send_body(handler, status, JSON_CONTENT_TYPE, compact_json(payload).encode("utf-8"))


def json_text_response(handler: BaseHTTPRequestHandler, body: str) -> None:
    """Send an already-encoded JSON document (e.g. a stored envelope) with 200."""
    send_body(handler, HTTPStatus.OK, JSON_CONTENT_TYPE, body.encode("utf-8"))


def read_json_request(handler: BaseHTTPRequestHandler, max_bytes: int = MAX_ENVELOPE_BYTES) -> Any:
    """Read and decode the JSON request body.

    Raises ``ValueError`` with one of ``missing_content_length``,
    ``bad_content_length``, ``payload_too_large`` or ``invalid_json``.
    """
    length = handler.headers.get("Content-Length")
    if not length:
        raise ValueError("missing_content_length")
    try:
        size = int(length)
    except ValueError as exc:
        raise ValueError("bad_content_length") from exc
    if size < 0 or size > max_bytes:
        raise ValueError("payload_too_large")
    raw = handler.rfile.read(size)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError("invalid_json") from exc
