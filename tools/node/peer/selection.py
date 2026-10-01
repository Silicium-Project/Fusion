"""Peer selection for dispatch/replication: filtering by constraints and scoring."""

from __future__ import annotations

from typing import Any


class SelectionMixin:
    """Rank peers for a task according to roles, reputation and capacity."""

    def select_peers(
        self,
        *,
        required_roles: set[str] | None = None,
        limit: int = 0,
        require_relay: bool = False,
        exclude: set[str] | None = None,
        constraints: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Peers matching roles/relay/constraints, best score first."""
        exclude_ids = exclude or set()
        required_roles = required_roles or set()
        constraints = constraints or {}
        candidates: list[dict[str, Any]] = []
        for peer in self.peers_snapshot().get("peers", []):
            node_id = str(peer.get("node_id", ""))
            if not node_id or node_id in exclude_ids or peer.get("self"):
                continue
            if not self._peer_channel_matches(peer):
                continue
            peer_roles = {str(role).lower() for role in peer.get("roles", [])}
            if required_roles and not required_roles.intersection(peer_roles):
                continue
            if require_relay and not bool(peer.get("relay_capable", False)):
                continue
            if not self._peer_meets_constraints(peer, required_roles, constraints):
                continue
            candidates.append(peer)
        candidates.sort(key=lambda peer: self._peer_score(peer, required_roles), reverse=True)
        if limit > 0:
            return candidates[:limit]
        return candidates

    def _peer_meets_constraints(self, peer: dict[str, Any], required_roles: set[str], constraints: dict[str, float]) -> bool:
        status = str(peer.get("onchain_status", "")).strip().lower()
        if status and status not in {"active", "1", "workerstatus.active"}:
            return False
        checks = {
            "min_global_reputation": float(peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0)) or 0.0),
            "min_compute_reputation": float(peer.get("onchain_compute_reputation", 0.0) or 0.0),
            "min_verify_reputation": float(peer.get("onchain_verify_reputation", 0.0) or 0.0),
            "min_storage_reputation": float(peer.get("onchain_storage_reputation", 0.0) or 0.0),
            "min_stake_amount": float(peer.get("onchain_stake_amount", 0.0) or 0.0),
        }
        if "compute" in required_roles and checks["min_compute_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        if "verify" in required_roles and checks["min_verify_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        if "storage" in required_roles and checks["min_storage_reputation"] <= 0 and self.config.solana_reputation_enable:
            return False
        for key, actual in checks.items():
            minimum = float(constraints.get(key, 0.0) or 0.0)
            if minimum > 0 and actual < minimum:
                return False
        return True

    def _peer_score(self, peer: dict[str, Any], required_roles: set[str]) -> tuple[float, float, float]:
        capacity = peer.get("capacity", {}) if isinstance(peer.get("capacity"), dict) else {}
        reputation = float(peer.get("reputation_score", 0.0) or 0.0)
        resource_reputation = peer.get("resource_reputation") if isinstance(peer.get("resource_reputation"), dict) else {}
        dimensions = resource_reputation.get("dimensions") if isinstance(resource_reputation.get("dimensions"), dict) else {}
        if "verify" in required_roles:
            resource_dimension = "verify"
        elif "storage" in required_roles:
            resource_dimension = "storage"
        elif "compute" in required_roles:
            resource_dimension = "compute"
        else:
            resource_dimension = "delegation"
        role_memory = dimensions.get(resource_dimension) if isinstance(dimensions.get(resource_dimension), dict) else {}
        connection_memory = dimensions.get("connection") if isinstance(dimensions.get("connection"), dict) else {}
        role_combined = role_memory.get("combined") if isinstance(role_memory.get("combined"), dict) else {}
        connection_combined = connection_memory.get("combined") if isinstance(connection_memory.get("combined"), dict) else {}
        if "lower_bound" in role_combined:
            role_lower = float(role_combined.get("lower_bound", 0.0) or 0.0)
            connection_lower = float(connection_combined.get("lower_bound", role_lower) or role_lower)
            reputation = 100.0 * ((role_lower * 0.75) + (connection_lower * 0.25))
        if "verify" in required_roles:
            onchain_reputation = float(peer.get("onchain_verify_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        elif "storage" in required_roles:
            onchain_reputation = float(peer.get("onchain_storage_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        else:
            onchain_reputation = float(peer.get("onchain_compute_reputation", peer.get("onchain_global_reputation", peer.get("onchain_reputation", 0.0))) or 0.0)
        cpu = float(capacity.get("cpu_count", 0) or 0)
        disk_free = float(capacity.get("disk_free_bytes", 0) or 0)
        onchain_component = onchain_reputation * max(0.0, float(self.config.scheduler_onchain_weight))
        offchain_component = reputation * max(0.0, float(self.config.scheduler_offchain_weight))
        capacity_component = (cpu + (disk_free / max(1.0, 1024.0 * 1024.0 * 1024.0))) * max(
            0.0, float(self.config.scheduler_capacity_weight)
        )
        return (onchain_component, offchain_component, capacity_component)
