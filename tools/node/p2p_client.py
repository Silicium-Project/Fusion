"""Content fetch/put client over file, Silicium peers, HTTP(S) and an IPFS gateway."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from tools.node.util import sha256_bytes, stable_json

if TYPE_CHECKING:  # imported for annotations only; avoids an import cycle
    from tools.node.peer import PeerNetwork


class P2PClient:
    """Fetch and store content referenced by ``p2p_ref`` objects."""

    def __init__(self, gateway: str, export_dir: Path, peer_network: "PeerNetwork | None" = None) -> None:
        self.gateway = gateway.rstrip("/")
        self.export_dir = export_dir
        self.peer_network = peer_network

    def fetch(self, p2p_ref: Any) -> tuple[bytes, dict[str, Any]]:
        """Return ``(data, meta)`` for a content reference of any supported protocol."""
        if not p2p_ref:
            return b"", {"source": "none"}
        if not isinstance(p2p_ref, dict):
            raise ValueError("p2p_ref_not_object")

        # Results retain a local file reference for the producing node and a
        # portable content-addressed shared_ref. Prefer the latter whenever
        # this node has already received the artifact from the return path.
        shared_ref = p2p_ref.get("shared_ref")
        cached = self._fetch_shared_cache(shared_ref)
        if cached is not None:
            return cached

        protocol = str(p2p_ref.get("protocol", "ipfs")).lower()
        content_id = str(p2p_ref.get("content_id") or p2p_ref.get("cid") or p2p_ref.get("url") or "").strip()
        if not content_id:
            raise ValueError("missing_p2p_content_id")
        if protocol == "file":
            return self._fetch_file(content_id, shared_ref)
        if protocol == "silicium":
            return self._fetch_silicium(p2p_ref, content_id)
        if protocol in {"http", "https"}:
            return self._fetch_url(protocol, content_id)
        if protocol == "ipfs":
            return self._fetch_ipfs(content_id)
        # Unknown P2P protocols remain content-addressed references for now.
        return stable_json(p2p_ref).encode("utf-8"), {"source": protocol, "content_id": content_id}

    def _fetch_shared_cache(self, shared_ref: Any) -> tuple[bytes, dict[str, Any]] | None:
        if isinstance(shared_ref, dict):
            shared_id = str(shared_ref.get("content_id", "")).strip().lower()
            shared_path = self.export_dir / "p2p" / shared_id
            if len(shared_id) == 64 and shared_path.exists():
                data = shared_path.read_bytes()
                return data, {"source": "local-shared-cache", "content_id": shared_id, "size_bytes": len(data)}
        return None

    def _fetch_file(self, content_id: str, shared_ref: Any) -> tuple[bytes, dict[str, Any]]:
        path = Path(content_id).expanduser()
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            # put_local embeds an absolute path that is only valid on the
            # producing node. Cross-node consumers (verify handoff, pin,
            # reassembly) must follow shared_ref over the mesh instead.
            if isinstance(shared_ref, dict) and str(shared_ref.get("protocol", "")).lower() == "silicium":
                return self.fetch(shared_ref)
            raise
        return data, {"source": "file", "path": str(path), "size_bytes": len(data)}

    def _fetch_silicium(self, p2p_ref: dict[str, Any], content_id: str) -> tuple[bytes, dict[str, Any]]:
        if self.peer_network is None:
            raise ValueError("peer_network_not_configured")
        local_path = self.export_dir / "p2p" / content_id.lower()
        if len(content_id) == 64 and local_path.is_file():
            data = local_path.read_bytes()
            if sha256_bytes(data) == content_id.lower():
                return data, {
                    "source": "local-silicium-cache",
                    "content_id": content_id.lower(),
                    "size_bytes": len(data),
                }
        data, peer_meta = self.peer_network.fetch_content(content_id, str(p2p_ref.get("peer_id", "")).strip())
        # Scene/spec content is reused by every tile of a render. Cache a
        # verified fetch locally so subsequent tasks do not pay another
        # HTTPS/ICE handshake to the orchestrator.
        if len(content_id) == 64 and sha256_bytes(data) == content_id.lower():
            local_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = local_path.with_name(f".{content_id}.tmp-{os.getpid()}")
            temporary.write_bytes(data)
            temporary.replace(local_path)
        return data, self._silicium_fetch_meta(content_id, data, peer_meta)

    @staticmethod
    def _silicium_fetch_meta(content_id: str, data: bytes, peer_meta: dict[str, Any]) -> dict[str, Any]:
        meta = {
            "source": peer_meta.get("source", "silicium-peer"),
            "content_id": content_id,
            "peer_id": peer_meta.get("node_id", ""),
            "peer_url": peer_meta.get("http_base_url", ""),
            "size_bytes": len(data),
        }
        if peer_meta.get("transport_backend"):
            meta["transport_backend"] = peer_meta["transport_backend"]
        if peer_meta.get("transport_route"):
            meta["transport_route"] = peer_meta["transport_route"]
        if peer_meta.get("session_id"):
            meta["session_id"] = peer_meta["session_id"]
        if peer_meta.get("relayed_via"):
            meta["relayed_via"] = peer_meta.get("relayed_via", "")
        if isinstance(peer_meta.get("path_attestation"), dict):
            meta["path_attestation"] = peer_meta["path_attestation"]
        return meta

    @staticmethod
    def _fetch_url(protocol: str, content_id: str) -> tuple[bytes, dict[str, Any]]:
        with urllib.request.urlopen(content_id, timeout=15) as response:
            data = response.read()
        return data, {"source": protocol, "url": content_id, "size_bytes": len(data)}

    def _fetch_ipfs(self, content_id: str) -> tuple[bytes, dict[str, Any]]:
        if content_id.startswith("ipfs://"):
            content_id = content_id[len("ipfs://") :]
        url = f"{self.gateway}/api/v0/cat?arg={content_id}"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = response.read()
            return data, {"source": "ipfs", "cid": content_id, "size_bytes": len(data)}
        except urllib.error.URLError:
            local = self.export_dir / "p2p" / content_id
            if local.exists():
                data = local.read_bytes()
                return data, {"source": "local-p2p-cache", "cid": content_id, "size_bytes": len(data)}
            raise

    def put_local(
        self,
        data: bytes,
        *,
        replication_factor: int = 0,
        replication_quorum: int = 0,
        replication_roles: Iterable[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Store ``data`` content-addressed, announce it and optionally replicate it."""
        digest = sha256_bytes(data)
        path = self.export_dir / "p2p" / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        shared_ref = {"protocol": "silicium", "content_id": digest, "hash": "sha256:" + digest}
        replication: dict[str, Any] = {"attempted": 0, "stored": 0, "quorum": 0, "satisfied": True, "peers": []}
        if self.peer_network is not None:
            shared_ref["peer_id"] = self.peer_network.node_id
            self.peer_network.publish(
                "content_available",
                {"content_id": digest, "hash": "sha256:" + digest, "size_bytes": len(data)},
                # Availability gossip is advisory.  Never make the worker
                # wait for unreachable/NATed peers before returning a render
                # result; the anti-entropy loop will retry the announcement.
                background=True,
            )
            target_factor = max(0, int(replication_factor or 0))
            target_quorum = max(0, int(replication_quorum or 0))
            if target_factor > 0:
                replication = self.peer_network.replicate_content(
                    digest,
                    data,
                    target_factor=target_factor,
                    required_quorum=target_quorum or target_factor,
                    required_roles=replication_roles or {"storage"},
                    constraints=constraints,
                )
                shared_ref["replication"] = replication
        return {
            "protocol": "file",
            "content_id": str(path),
            "hash": "sha256:" + digest,
            "size_bytes": len(data),
            "shared_ref": shared_ref,
            "replication": replication,
        }

    def pin(self, p2p_ref: Any) -> dict[str, Any]:
        """Fetch a reference and keep a local copy."""
        data, meta = self.fetch(p2p_ref)
        stored = self.put_local(data)
        return {"source": meta, "stored_ref": stored}

    def unpin(self, p2p_ref: Any) -> dict[str, Any]:
        """Remove a local copy."""
        if not isinstance(p2p_ref, dict):
            raise ValueError("p2p_ref_not_object")
        content_id = str(p2p_ref.get("content_id") or p2p_ref.get("cid") or "").strip()
        path = self.export_dir / "p2p" / content_id
        existed = path.exists()
        if existed:
            path.unlink()
        return {"content_id": content_id, "removed": existed}
