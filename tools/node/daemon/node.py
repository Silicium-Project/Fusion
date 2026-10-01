"""NetworkNode: assembles the daemon mixins and owns construction and the main loop."""

from __future__ import annotations

import threading
import time
from typing import Any

from tools.node.config import NodeConfig
from tools.node.daemon.claims import ClaimsMixin
from tools.node.daemon.dispatch import DispatchMixin
from tools.node.daemon.execution import ExecutionMixin
from tools.node.daemon.handling import HandlingMixin
from tools.node.daemon.heartbeat import HeartbeatMixin
from tools.node.daemon.onchain import OnchainSubmitMixin
from tools.node.daemon.onchain_profile import OnchainProfileMixin
from tools.node.daemon.progress import ProgressMixin
from tools.node.daemon.pull_loop import PullLoopMixin
from tools.node.daemon.queue import QueueMixin
from tools.node.daemon.receipts import ReceiptsMixin
from tools.node.daemon.reconcile import ReconcileMixin
from tools.node.daemon.task_control import TaskControlMixin
from tools.node.daemon.task_snapshots import TaskSnapshotsMixin
from tools.node.p2p_client import P2PClient
from tools.node.peer import PeerNetwork
from tools.node.queue_state import QueueState
from tools.node.reputation import ReputationStore
from tools.node.role_runtime import RoleRuntime
from tools.node.solana_bridge import SolanaBridge
from tools.node.util import append_jsonl, read_json, safe_id, safe_path_id, utc_now
from tools.resource_intelligence import build_resource_profile
from tools.runtime_telemetry import RuntimeTelemetrySampler


class NetworkNode(
    OnchainProfileMixin,
    HeartbeatMixin,
    QueueMixin,
    TaskControlMixin,
    ReceiptsMixin,
    ProgressMixin,
    ReconcileMixin,
    TaskSnapshotsMixin,
    HandlingMixin,
    ExecutionMixin,
    DispatchMixin,
    ClaimsMixin,
    PullLoopMixin,
    OnchainSubmitMixin,
):
    """Role-aware node daemon: consumes queues, executes, dispatches and reports."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.state = QueueState(config.state_dir)
        node_path_id = safe_path_id(safe_id(config.node_id))
        self.reputation = ReputationStore(
            config.export_dir / f"node.{node_path_id}.reputation.json",
            initial_score=config.reputation_score,
            resource_profile=build_resource_profile(config.export_dir),
        )
        self.config.reputation_score = self.reputation.local_score()
        self.peer_network = PeerNetwork(config, config.export_dir)
        # Back-reference used by the peer layer for task controls and claims.
        self.peer_network.node = self
        self.peer_network.set_peer_score_sink(self.reputation.set_peer_score)
        self.p2p = P2PClient(config.p2p_gateway, config.export_dir, self.peer_network)
        self.solana = SolanaBridge(config)
        self.runtime = RoleRuntime(config, self.p2p)
        self.events_path = config.export_dir / "node.events.ndjson"
        self.heartbeat_path = config.export_dir / f"node.{node_path_id}.heartbeat.json"
        self.metrics_path = config.export_dir / f"node.{node_path_id}.metrics.json"
        self.metrics = read_json(
            self.metrics_path,
            {"schema_version": 1, "handled": 0, "failed": 0, "retried": 0, "dead_lettered": 0, "dispatched": 0, "dispatch_failed": 0},
        )
        self._init_onchain_state()
        self._init_claim_state()
        self._init_activity_state()
        self.telemetry_sampler = RuntimeTelemetrySampler(config.export_dir)
        self._telemetry: dict[str, Any] = self.telemetry_sampler.sample()
        self._task_monitor_stop = threading.Event()
        self._task_monitor_thread: threading.Thread | None = None
        self._load_task_controls()
        self.peer_network.set_local_profile(
            capacity=self.runtime.capacity(),
            reputation_score=self.reputation.local_score(),
            resource_reputation=self.reputation.resource_snapshot(),
            activity=self.activity_snapshot(),
            task_queue=self.cached_task_queue_snapshot(),
        )

    def _init_onchain_state(self) -> None:
        self._last_reputation_refresh_unix = 0.0
        self._last_peer_reputation_refresh_unix = 0.0
        self._solana_owner = ""
        self._solana_worker = ""
        self._solana_onchain_reputation = 0.0
        self._solana_onchain_compute_reputation = 0.0
        self._solana_onchain_verify_reputation = 0.0
        self._solana_onchain_storage_reputation = 0.0
        self._solana_onchain_stake_amount = 0.0
        self._solana_onchain_status = ""

    def _init_claim_state(self) -> None:
        self._pull_thread: threading.Thread | None = None
        self._pull_stop_event = threading.Event()
        # Claiming must be atomic across HTTP handlers, but it must not block
        # peer discovery/heartbeat handlers on the broader P2P lock.
        self._task_claim_lock = threading.Lock()
        self._claim_pending_envelopes: list[dict[str, Any]] = []
        self._queue_recovery_attempted = False
        self._last_claim_poll_unix = 0.0
        self._last_claim_poll_utc = ""
        self._last_claim_error = ""
        self._last_claim_result = "not_started"
        self._last_claim_targets: list[dict[str, Any]] = []

    def _init_activity_state(self) -> None:
        self._activity_lock = threading.Lock()
        self._active_tasks: list[dict[str, Any]] = []
        self._last_response: dict[str, Any] = {}
        self._task_queue_cache_lock = threading.Lock()
        self._task_queue_cache: list[dict[str, Any]] = []
        self._task_queue_cache_generation = 0
        self._task_queue_cache_updated_monotonic = 0.0
        self._task_queue_cache_refreshing = False

    def run(self) -> None:
        """Start the peer layer and loop: heartbeat, sweep, save, metrics (once or forever)."""
        self.peer_network.start()
        if self.config.once and self.config.remote_dispatch_enable:
            # One-shot dispatch has no later convergence cycle to wait for.
            self.peer_network.sync_once()
        if self.config.pull_tasks_enable:
            self._start_pull_tasks_loop()
        try:
            self.bootstrap()
            self.refresh_local_onchain_profile(force=True)
            while True:
                self.write_heartbeat()
                handled = self.sweep()
                self.state.save()
                self.write_metrics()
                self.write_heartbeat()
                if self.config.once:
                    return
                if handled == 0:
                    time.sleep(max(0, self.config.idle_ms) / 1000.0)
        finally:
            self._stop_pull_tasks_loop()
            self.peer_network.stop()

    def bootstrap(self) -> None:
        """Register the worker on-chain when ``--bootstrap-worker`` is set."""
        if not self.config.bootstrap_worker:
            return
        result = self.solana.call("register_worker", {})
        append_jsonl(
            self.events_path,
            {
                "schema_version": 1,
                "timestamp_utc": utc_now(),
                "node_id": self.config.node_id,
                "kind": "bootstrap",
                "ok": bool(result.get("ok", True)),
                "solana": result,
            },
        )
