"""Shortest-path route table over attested peer links (Dijkstra)."""

from __future__ import annotations

import heapq
from typing import Any, Mapping

from tools.node.util import atomic_write_json, utc_now


# Edge cost per attested route kind: direct links are preferred over relays,
# and the central (rendezvous HTTP) path is the expensive fallback.
ROUTE_WEIGHTS = {"direct": 1.0, "relay": 2.0, "central": 8.0, "peer-http": 8.0}


class RoutingMixin:
    """Compute the routed view of the mesh from transport attestations."""

    def route_table_snapshot(self) -> list[dict[str, Any]]:
        """Compute shortest known peer paths, preferring direct ICE/UDP links."""
        with self._lock:
            peers = {
                str(peer.get("node_id", "")): dict(peer)
                for peer in self._peers.values()
                if peer.get("node_id") and self._peer_channel_matches(peer)
            }
        peers[self.node_id] = {"node_id": self.node_id}
        graph = self._route_graph(peers)
        distances, previous = self._shortest_paths(graph)
        routes: list[dict[str, Any]] = []
        for target in sorted(node_id for node_id in peers if node_id != self.node_id):
            routes.append(self._route_entry(target, distances, previous))
        atomic_write_json(self.routes_path, {"schema_version": 1, "node_id": self.node_id, "routes": routes, "updated_utc": utc_now()})
        return routes

    def _route_graph(self, peers: dict[str, dict[str, Any]]) -> dict[str, list[tuple[float, str, str]]]:
        """Weighted edges: successful attested routes, plus central HTTP fallbacks."""
        graph: dict[str, list[tuple[float, str, str]]] = {node_id: [] for node_id in peers}
        for observer, peer in peers.items():
            attestations = peer.get("transport_attestations", [])
            if not isinstance(attestations, list):
                attestations = []
            for claim in attestations:
                if not isinstance(claim, Mapping) or not bool(claim.get("success", False)):
                    continue
                target = str(claim.get("remote_peer_id", "")).strip()
                route = str(claim.get("route", "")).strip().lower()
                if target not in peers or route not in ROUTE_WEIGHTS:
                    continue
                graph.setdefault(observer, []).append((ROUTE_WEIGHTS[route], target, route))
            if observer != self.node_id and str(peer.get("http_base_url", "")).strip():
                graph.setdefault(self.node_id, []).append((ROUTE_WEIGHTS["central"], observer, "central"))
        return graph

    def _shortest_paths(
        self, graph: dict[str, list[tuple[float, str, str]]]
    ) -> tuple[dict[str, float], dict[str, tuple[str, str]]]:
        """Dijkstra from this node: (distance per node, predecessor and route kind)."""
        distances: dict[str, float] = {self.node_id: 0.0}
        previous: dict[str, tuple[str, str]] = {}
        queue: list[tuple[float, str]] = [(0.0, self.node_id)]
        while queue:
            cost, current = heapq.heappop(queue)
            if cost != distances.get(current):
                continue
            for edge_cost, target, route in graph.get(current, []):
                candidate = cost + edge_cost
                if candidate < distances.get(target, float("inf")):
                    distances[target] = candidate
                    previous[target] = (current, route)
                    heapq.heappush(queue, (candidate, target))
        return distances, previous

    def _route_entry(
        self,
        target: str,
        distances: dict[str, float],
        previous: dict[str, tuple[str, str]],
    ) -> dict[str, Any]:
        if target not in distances:
            return {"target_peer_id": target, "reachable": False, "path": [], "cost": None, "hops": 0}
        path = [target]
        route_kinds: list[str] = []
        cursor = target
        while cursor != self.node_id:
            parent, route = previous[cursor]
            route_kinds.append(route)
            path.append(parent)
            cursor = parent
        path.reverse()
        route_kinds.reverse()
        return {
            "target_peer_id": target,
            "reachable": True,
            "path": path,
            "next_hop": path[1] if len(path) > 1 else target,
            "hops": len(path) - 1,
            "cost": distances[target],
            "transport": route_kinds[-1] if route_kinds else "local",
        }
