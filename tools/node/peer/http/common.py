"""Helpers shared by the peer HTTP route modules (JSON bodies and responses)."""

from __future__ import annotations

import json
from typing import Any

from tools.node.util import stable_json

JSON_CONTENT_TYPE = "application/json; charset=utf-8"
# Literal body kept byte-identical to the historical responses.
OK_BODY = b'{"ok":true}'


def read_json_object(handler: Any, raw: bytes, *, allow_empty: bool = False) -> dict[str, Any] | None:
    """Decode a JSON object body, answering 400 and returning None otherwise.

    With ``allow_empty`` an empty body is treated as ``{}`` (session actions
    and task claims accept bodiless POSTs).
    """
    try:
        payload = json.loads(raw.decode("utf-8")) if raw or not allow_empty else {}
    except Exception:
        handler.send_error(400)
        return None
    if not isinstance(payload, dict):
        handler.send_error(400)
        return None
    return payload


def send_json(handler: Any, status: int, payload: Any, *, cache_control: str | None = None) -> None:
    """Answer with ``payload`` encoded as canonical (sorted, compact) JSON."""
    handler.send_body(status, stable_json(payload).encode("utf-8"), cache_control=cache_control)
