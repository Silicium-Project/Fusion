"""Software update announcements: validate, persist, list, fetch and reconcile."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tools.node.util import (
    atomic_write_json,
    read_json,
    safe_id,
    safe_path_id,
    sha256_bytes,
    utc_now,
)


class UpdatesMixin:
    """Relay signed software update manifests and their content."""

    def _seed_local_update_manifests(self) -> None:
        paths: list[Path] = []
        env_manifest = os.environ.get("SILICIUM_UPDATE_MANIFEST_PATH", "").strip()
        if env_manifest:
            paths.append(Path(env_manifest))
        for filename in ("update.manifest.json", "manifest.json"):
            candidate = self.export_dir / filename
            if candidate not in paths:
                paths.append(candidate)

        for path in paths:
            if not path.is_file():
                continue
            payload = read_json(path, None)
            if not payload:
                continue
            if isinstance(payload, dict):
                releases = payload.get("releases", [payload]) if "releases" in payload else [payload]
                for release in releases:
                    if isinstance(release, dict):
                        self._record_update_announcement(release, source_peer_id="local_disk")

    @staticmethod
    def _normalize_update_announcement(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        channel = str(payload.get("channel", "")).strip().lower()
        version = str(payload.get("version", "")).strip()
        digest = str(payload.get("sha256", "")).strip().lower()
        content_id = str(payload.get("content_id", digest)).strip().lower()
        signature = str(payload.get("signature", "")).strip()
        try:
            size_bytes = int(payload.get("size_bytes", 0) or 0)
            check_interval = max(15, int(payload.get("check_interval_seconds", 0) or 0))
        except (TypeError, ValueError):
            return None
        if channel not in {"dev", "prod"} or not version or len(version) > 80:
            return None
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            return None
        if content_id != digest or size_bytes <= 0 or size_bytes > 1024 * 1024 * 1024:
            return None
        if not signature or len(signature) > 256:
            return None
        return {
            "schema_version": 1,
            "channel": channel,
            "version": version,
            "platform": str(payload.get("platform", "")).strip().lower(),
            "url": str(payload.get("url", "")).strip(),
            "sha256": digest,
            "content_id": content_id,
            "size_bytes": size_bytes,
            "auto_install": bool(payload.get("auto_install", True)),
            "check_interval_seconds": check_interval,
            "signature": signature,
            "signing_key_id": str(payload.get("signing_key_id", "")).strip(),
        }

    def _record_update_announcement(self, payload: Any, source_peer_id: str) -> bool:
        release = self._normalize_update_announcement(payload)
        if release is None:
            return False
        if release["channel"] != self.config.release_channel:
            return False
        release["source_peer_id"] = safe_id(source_peer_id) if source_peer_id else ""
        release["observed_utc"] = utc_now()
        target = (
            self.update_announcements_dir
            / release["channel"]
            / f"{safe_path_id(release['version'])}-{release['content_id']}.json"
        )
        atomic_write_json(target, release)
        return True

    def update_announcements(self) -> list[dict[str, Any]]:
        """Validated update announcements of our channel (at most 64)."""
        releases: list[dict[str, Any]] = []
        if self.update_announcements_dir.exists():
            for path in self.update_announcements_dir.glob("*/*.json"):
                payload = read_json(path, {})
                normalized = self._normalize_update_announcement(payload)
                if normalized is None or normalized["channel"] != self.config.release_channel:
                    continue
                normalized["source_peer_id"] = str(payload.get("source_peer_id", ""))
                normalized["observed_utc"] = str(payload.get("observed_utc", ""))
                normalized["cached"] = (self.export_dir / "p2p" / normalized["content_id"]).is_file()
                releases.append(normalized)
        releases.sort(key=lambda item: (str(item.get("channel", "")), str(item.get("version", "")), str(item.get("observed_utc", ""))))
        return releases[-64:]

    def fetch_update_content(self, content_id: str) -> bytes:
        """Bytes of an announced update, fetched from peers and cached if needed."""
        normalized = str(content_id).strip().lower()
        if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
            raise ValueError("update_content_id_invalid")
        known = [release for release in self.update_announcements() if release.get("content_id") == normalized]
        if not known:
            raise FileNotFoundError("update_announcement_not_found")
        target = self.export_dir / "p2p" / normalized
        if target.is_file():
            data = target.read_bytes()
        else:
            preferred_peer_id = str(known[-1].get("source_peer_id", ""))
            data, _meta = self.fetch_content(normalized, preferred_peer_id)
            expected_size = int(known[-1].get("size_bytes", 0) or 0)
            if expected_size > 0 and len(data) != expected_size:
                raise ValueError("update_size_mismatch")
            if sha256_bytes(data) != normalized:
                raise ValueError("update_sha256_mismatch")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
            self.publish(
                "software_update_cached",
                {"content_id": normalized, "size_bytes": len(data), "cached_by": self.node_id},
            )
        if sha256_bytes(data) != normalized:
            raise ValueError("update_sha256_mismatch")
        return data

    def _sync_update_manifest(self, base_url: str) -> None:
        """Reconcile durable update announcements after transient gossip loss."""
        path = "/updates/manifest"
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            headers=self._signed_headers("GET", path, b""),
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        releases = payload.get("releases")
        if not isinstance(releases, list):
            return
        source_peer_id = str(payload.get("node_id", "")).strip()
        known = {
            (str(item.get("channel", "")), str(item.get("version", "")), str(item.get("content_id", "")))
            for item in self.update_announcements()
        }
        for release in releases:
            normalized = self._normalize_update_announcement(release)
            if normalized is None:
                continue
            key = (normalized["channel"], normalized["version"], normalized["content_id"])
            if key in known:
                continue
            if self._record_update_announcement(normalized, source_peer_id):
                known.add(key)
