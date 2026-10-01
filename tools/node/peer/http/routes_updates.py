"""Software update routes: manifest, cached content download and cache upload."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlparse

from tools.node.peer.http.common import send_json
from tools.node.util import sha256_bytes


def get_manifest(handler: Any, peer: Any) -> None:
    """Known update announcements of this release channel (loopback or signed)."""
    if not handler._local_or_authorized():
        handler.send_error(403)
        return
    send_json(
        handler,
        200,
        {
            "schema_version": 1,
            "source": "silicium-gossip",
            "node_id": peer.node_id,
            "releases": peer.update_announcements(),
        },
        cache_control="no-store",
    )


def get_content(handler: Any, peer: Any) -> None:
    """Serve (fetching from peers if needed) an announced update artifact."""
    if not handler._local_or_authorized():
        handler.send_error(403)
        return
    content_id = unquote(urlparse(handler.path).path[len("/updates/content/") :]).strip()
    try:
        raw = peer.fetch_update_content(content_id)
    except FileNotFoundError:
        handler.send_error(404)
        return
    except (OSError, ValueError):
        handler.send_error(502)
        return
    handler.send_body(
        200,
        raw,
        content_type="application/octet-stream",
        cache_control="private, max-age=31536000, immutable",
    )


def post_cache(handler: Any, peer: Any, raw: bytes) -> None:
    """Store an update artifact whose sha256 matches the URL (caller pre-authorised)."""
    content_id = unquote(urlparse(handler.path).path[len("/updates/cache/") :]).strip().lower()
    if (
        len(content_id) != 64
        or any(char not in "0123456789abcdef" for char in content_id)
        or len(raw) > 1024 * 1024 * 1024
        or sha256_bytes(raw) != content_id
    ):
        handler.send_error(400)
        return
    target = peer.export_dir / "p2p" / content_id
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(raw)
    peer.publish(
        "software_update_cached",
        {"content_id": content_id, "size_bytes": len(raw), "cached_by": peer.node_id},
    )
    send_json(handler, 200, {"ok": True, "content_id": content_id})
