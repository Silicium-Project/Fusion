"""Local reputation store: score history, peer scores and the resource Bayes memory."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Mapping

from tools.node.util import atomic_write_json, read_json, utc_now
from tools.resource_intelligence import DualMemoryBayes, resource_baselines


class ReputationStore:
    """Thread-safe JSON store of the node's local reputation state."""

    def __init__(self, path: Path, initial_score: float = 0.0, resource_profile: Mapping[str, Any] | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        loaded = read_json(path, {})
        self._payload = loaded if isinstance(loaded, dict) else {}
        self._payload["schema_version"] = max(2, int(self._payload.get("schema_version", 1) or 1))
        self._payload.setdefault("local_score", float(initial_score))
        self._payload.setdefault("peer_scores", {})
        self._payload.setdefault("history", [])
        self._payload.setdefault(
            "resource_memory",
            DualMemoryBayes(baselines=resource_baselines(resource_profile)).export_state(),
        )
        self.save()

    def local_score(self) -> float:
        """Current local reputation score."""
        with self._lock:
            return float(self._payload.get("local_score", 0.0) or 0.0)


    def adjust_local(self, delta: float, reason: str) -> float:
        """Add ``delta`` to the local score (history kept to 512 entries)."""
        with self._lock:
            score = float(self._payload.get("local_score", 0.0) or 0.0) + float(delta)
            self._payload["local_score"] = score
            history = self._payload.get("history", [])
            if not isinstance(history, list):
                history = []
            history.append({"timestamp_utc": utc_now(), "delta": float(delta), "reason": reason})
            self._payload["history"] = history[-512:]
        self.save()
        return score

    def set_peer_score(self, node_id: str, score: float) -> None:
        """Record the last known score of a peer."""
        if not node_id:
            return
        with self._lock:
            peers = self._payload.get("peer_scores", {})
            if not isinstance(peers, dict):
                peers = {}
            peers[node_id] = float(score)
            self._payload["peer_scores"] = peers
        self.save()

    def observe_resource(
        self,
        dimension: str,
        success: bool,
        *,
        weight: float = 1.0,
        event_class: str = "verified",
    ) -> dict[str, Any]:
        """Feed one outcome to the resource Bayes memory; return its snapshot."""
        with self._lock:
            model = DualMemoryBayes(self._payload.get("resource_memory"))
            model.observe(dimension, success, weight=weight, event_class=event_class)
            self._payload["resource_memory"] = model.export_state()
            snapshot = model.snapshot()
        self.save()
        return snapshot

    def observe_uptime(
        self,
        uptime_seconds: float,
        corroborated_peer_count: int = 1,
        *,
        self_reported_only: bool = False,
        now: float | None = None,
    ) -> float:
        """Feed an uptime observation; return the weight applied."""
        with self._lock:
            model = DualMemoryBayes(self._payload.get("resource_memory"))
            weight = model.observe_uptime(
                uptime_seconds,
                corroborated_peer_count=corroborated_peer_count,
                self_reported_only=self_reported_only,
                now=now,
            )
            self._payload["resource_memory"] = model.export_state()
        self.save()
        return weight

    def resource_snapshot(self) -> dict[str, Any]:
        """Snapshot of the resource Bayes memory."""
        with self._lock:
            model = DualMemoryBayes(self._payload.get("resource_memory"))
        return model.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Deep copy of the stored payload."""
        with self._lock:
            return json.loads(json.dumps(self._payload, separators=(",", ":"), ensure_ascii=True))

    def save(self) -> None:
        """Persist the store atomically."""
        atomic_write_json(self._path, self.snapshot())
