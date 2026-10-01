"""PeerNetwork: assembles the peer mixins and owns construction, start and stop."""

from __future__ import annotations

import http.server
import importlib.util
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tools.direct_transport import (
    DirectTransportBackend,
    IceDirectTransport,
    NativeLightDirectTransport,
)
from tools.node.config import NodeConfig, build_capacity_snapshot
from tools.node.identity import NodeIdentity
from tools.node.peer.addressing import AddressingMixin
from tools.node.peer.announce import AnnounceMixin
from tools.node.peer.attestations import AttestationsMixin
from tools.node.peer.candidates import CandidatesMixin
from tools.node.peer.content import ContentMixin
from tools.node.peer.direct import DirectSessionsMixin
from tools.node.peer.gossip import GossipMixin
from tools.node.peer.handshake import HandshakeMixin
from tools.node.peer.http.server import HttpServerMixin
from tools.node.peer.messages import MessagesMixin
from tools.node.peer.peer_table import PeerTableMixin
from tools.node.peer.routing import RoutingMixin
from tools.node.peer.security import SecurityMixin
from tools.node.peer.selection import SelectionMixin
from tools.node.peer.signaling import SignalingMixin
from tools.node.peer.signaling_client import SignalingClientMixin
from tools.node.peer.sync import SyncMixin
from tools.node.peer.updates import UpdatesMixin
from tools.node.util import (
    atomic_write_json,
    normalize_release_channel,
    safe_id,
    safe_path_id,
    utc_now,
)
from tools.resource_intelligence import DualMemoryBayes


class PeerNetwork(
    PeerTableMixin,
    RoutingMixin,
    CandidatesMixin,
    AttestationsMixin,
    SignalingMixin,
    SignalingClientMixin,
    AnnounceMixin,
    UpdatesMixin,
    GossipMixin,
    ContentMixin,
    DirectSessionsMixin,
    HandshakeMixin,
    SelectionMixin,
    MessagesMixin,
    SyncMixin,
    AddressingMixin,
    SecurityMixin,
    HttpServerMixin,
):
    """Peer-to-peer layer of a node (HTTP gossip, UDP, signaling, ICE, content)."""

    def __init__(self, config: NodeConfig, export_dir: Path) -> None:
        self.config = config
        self.config.release_channel = normalize_release_channel(self.config.release_channel, default="dev")
        self.export_dir = export_dir
        self.node_id = safe_id(config.node_id)
        self.identity = NodeIdentity(config)
        self.node_path_id = safe_path_id(self.node_id)
        self._init_export_paths(export_dir)
        self._init_runtime_state()
        self._init_local_profile(config)
        self._last_candidate_refresh_unix = 0.0
        self._observed_public_address = ""
        self._nat_behavior = "unknown"
        self.direct_transport = self._build_direct_transport_backend()

    def _init_export_paths(self, export_dir: Path) -> None:
        """Files this peer writes in the export directory (read by the BackEnd)."""
        self.peers_path = export_dir / f"node.{self.node_path_id}.peers.json"
        self.routes_path = export_dir / f"node.{self.node_path_id}.routes.json"
        self.candidates_path = export_dir / "p2p.candidates.json"
        self.sessions_path = export_dir / "p2p.sessions.json"
        self.session_events_path = export_dir / "p2p.sessions.ndjson"
        self.direct_sessions_path = export_dir / "p2p.direct_sessions.json"
        self.transport_attestations_path = export_dir / "p2p.transport_attestations.json"
        self.transport_attestation_events_path = export_dir / "p2p.transport_attestations.ndjson"
        self.gossip_events_path = export_dir / "gossip.events.ndjson"
        self.task_control_events_path = export_dir / "gossip.task-controls.ndjson"
        self.update_announcements_dir = export_dir / "software-updates"
        self.discovery_registry_path = export_dir / "mesh.discovery.json"

    def _init_runtime_state(self) -> None:
        """In-memory tables, locks and background worker handles."""
        self._peers: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._direct_sessions: dict[str, dict[str, Any]] = {}
        self._transport_attestations: list[dict[str, Any]] = []
        self._ice_content_sessions: dict[str, str] = {}
        self._signaling_ready_payloads: dict[str, dict[str, Any]] = {}
        self._started_direct_sessions: set[str] = set()
        self._local_candidates: list[dict[str, Any]] = []
        self._seen_events: set[str] = set()
        self._verified_transport_claims: set[str] = set()
        self._seen_handshake_nonces: dict[str, float] = {}
        self._seen_punch_nonces: set[str] = set()
        self._lock = threading.RLock()
        self._http_server: http.server.HTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._udp_socket: socket.socket | None = None
        self._udp_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._announce_schedule_lock = threading.Lock()
        self._announce_scheduled = False
        self._gossip_forward_lock = threading.Lock()
        self._gossip_forward_executor: ThreadPoolExecutor | None = None
        self._stop_event = threading.Event()
        self._peer_score_sink: Any = None
        self.http_base_url = ""
        self.advertised_http_base_url = ""
        self.mesh_post_url = ""

    def _init_local_profile(self, config: NodeConfig) -> None:
        """Profile announced to peers; refreshed by NetworkNode heartbeats."""
        self.local_capacity = build_capacity_snapshot(config)
        self.local_reputation_score = float(config.reputation_score)
        self.local_resource_reputation: dict[str, Any] = DualMemoryBayes().snapshot()
        self.local_activity: dict[str, Any] = {
            "status": "idle",
            "active_tasks": [],
            "last_response": {},
        }
        self.local_task_queue: list[dict[str, Any]] = []
        self.local_onchain_reputation = 0.0
        self.local_onchain_global_reputation = 0.0
        self.local_onchain_compute_reputation = 0.0
        self.local_onchain_verify_reputation = 0.0
        self.local_onchain_storage_reputation = 0.0
        self.local_onchain_stake_amount = 0.0
        self.local_onchain_status = ""
        self.local_solana_owner = ""
        self.local_solana_worker = ""

    def _build_direct_transport_backend(self) -> DirectTransportBackend:
        backend_name = str(self.config.p2p_direct_transport_backend or "auto").strip().lower()
        if backend_name in {"", "auto", "automatic"}:
            backend_name = "ice" if importlib.util.find_spec("aioice") is not None else "native-light"
        if backend_name in {"native-light", "native_light", "native"}:
            return NativeLightDirectTransport(self, safe_id=safe_id, utc_now=utc_now, atomic_write_json=atomic_write_json)
        if backend_name in {"ice", "aioice", "ice-stun-turn"}:
            return IceDirectTransport(self, safe_id=safe_id, utc_now=utc_now, atomic_write_json=atomic_write_json)
        raise ValueError(f"unsupported_direct_transport_backend:{backend_name}")

    def start(self) -> None:
        # Upgrade old general gossip logs before any listener can append a new
        # control and accidentally make the dedicated index look complete.
        """Start listeners, load persisted state and begin background sync."""
        self.recent_task_control_events(2048)
        self._start_http_server()
        self._seed_local_update_manifests()
        if self.config.gossip_enable:
            self._start_udp_listener()
        self._load_persisted_peers()
        self._load_persisted_sessions()
        self._load_transport_attestations()
        self.refresh_candidates(force=True)
        self._record_self_peer()
        if self.config.peer_sync_interval_s > 0:
            self._start_sync_loop()
        # A peer may be unreachable during startup.  Announcements and the
        # initial HTTP sync each have network timeouts, so run them outside the
        # critical path: callers can publish a heartbeat as soon as the local
        # HTTP service is listening.
        threading.Thread(
            target=self._announce_and_sync_initial,
            name=f"silicium-peer-bootstrap-{self.node_id}",
            daemon=True,
        ).start()

    def _announce_and_sync_initial(self) -> None:
        try:
            self.announce()
            self.sync_once()
        except Exception:
            # Peer convergence is best-effort and retried by the periodic sync
            # loop; it must never prevent a node from becoming ready.
            return

    def stop(self) -> None:
        """Stop listeners, background threads and the transport backend."""
        self._stop_event.set()
        self.direct_transport.close()
        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=1)
            self._http_thread = None
        if self._udp_socket is not None:
            try:
                self._udp_socket.close()
            except OSError:
                pass
            self._udp_socket = None
        if self._udp_thread is not None:
            self._udp_thread.join(timeout=1)
            self._udp_thread = None
        if self._sync_thread is not None:
            self._sync_thread.join(timeout=1)
            self._sync_thread = None
        with self._gossip_forward_lock:
            gossip_executor = self._gossip_forward_executor
            self._gossip_forward_executor = None
        if gossip_executor is not None:
            gossip_executor.shutdown(wait=False, cancel_futures=True)
