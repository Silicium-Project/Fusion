//! What every workload execution shares: the node context, and the HTTP
//! helpers for the local daemons (compute daemon, reputation bridge).
//! Workload-specific execution is in [`crate::workload`]; task-book
//! bookkeeping (claim, lease, result) is in [`crate::worker`].

use crate::{
    activity::ActivityLog,
    content::ContentStore,
    jobs::JobSettings,
    peers::{LocalRoles, WorkerView},
    storage::TaskBookState,
    task::NetworkTask,
};
use libp2p::PeerId;
use silicium_node_core::{
    beta::BetaPosterior, hardware::HardwareBucket, p2p::DhtRecordEnvelope, taskbook::TaskEvent,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    env,
    sync::{
        Arc, Mutex,
        atomic::{AtomicUsize, Ordering},
    },
    time::Duration,
};
use tokio::sync::mpsc;

#[derive(Clone)]
pub(crate) struct NodeContext {
    pub(crate) local_peer_id: PeerId,
    pub(crate) hardware: HardwareBucket,
    pub(crate) dispatcher_seed: u64,
    pub(crate) taskbook: TaskBookState,
    pub(crate) tx_events: mpsc::Sender<TaskEvent>,
    /// Tasks recursively delegated by a worker that split its accepted task.
    pub(crate) tx_publish: mpsc::Sender<NetworkTask>,
    pub(crate) job_settings: JobSettings,
    /// Upper bound of one compute call, in seconds.
    pub(crate) compute_timeout_s: u64,
    /// Tasks this node knows (received or published), by task id: what a
    /// verifier needs to re-render milestones.
    pub(crate) known_tasks: Arc<Mutex<BTreeMap<String, NetworkTask>>>,
    /// Scenes and result images shared with peers, inside the compute work
    /// directory.
    pub(crate) content: ContentStore,
    /// Other workers visible through direct connections or fresh signed
    /// gossip, refreshed by the event loop.
    pub(crate) online_workers: Arc<AtomicUsize>,
    /// Task-book identities of live compute peers advertised through the
    /// gossip mesh, used by the Bayesian delegation decision.
    pub(crate) available_compute_authors: Arc<Mutex<Vec<Option<String>>>>,
    /// Free compute slots: a worker claims a task only once it holds one.
    pub(crate) compute_slots: Arc<tokio::sync::Semaphore>,
    /// Roles of this node (`SILICIUM_NODE_ROLES`).
    pub(crate) roles: LocalRoles,
    /// Tasks being handled by [`crate::worker::process_task`]: a task
    /// announced again while it is handled is not claimed twice.
    pub(crate) active_tasks: Arc<Mutex<BTreeSet<String>>>,
    /// Tasks awaiting their parent/proposal events during delegated admission.
    pub(crate) pending_admissions: Arc<Mutex<BTreeSet<String>>>,
    /// Work in progress and work journal shown by the desktop app.
    pub(crate) activity: ActivityLog,
    /// Data directory of the node (identity, task book, models).
    pub(crate) data_dir: std::path::PathBuf,
}

impl NodeContext {
    /// Workers seen by this node now (see [`crate::peers`]).
    pub(crate) fn worker_view(&self) -> WorkerView {
        WorkerView {
            others: self.online_workers.load(Ordering::Relaxed),
            local_is_worker: self.roles.is_worker(),
        }
    }

    /// Remembers a task for later verification.
    pub(crate) fn remember_task(&self, task: &NetworkTask) {
        if let Ok(mut known) = self.known_tasks.lock() {
            known.insert(task.task_id.clone(), task.clone());
        }
    }
}

/// HTTP client for the local daemons: every call is bounded in time, and the
/// compute daemon token (`SILICIUM_COMPUTE_TOKEN`) is sent when configured.
pub(crate) fn daemon_client(timeout_s: u64) -> Result<reqwest::Client, reqwest::Error> {
    let mut headers = reqwest::header::HeaderMap::new();
    if let Ok(token) = env::var("SILICIUM_COMPUTE_TOKEN")
        && let Ok(value) =
            reqwest::header::HeaderValue::from_str(&format!("Bearer {}", token.trim()))
    {
        headers.insert(reqwest::header::AUTHORIZATION, value);
    }
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(timeout_s.saturating_add(30)))
        .default_headers(headers)
        .build()
}

pub(crate) fn compute_url() -> String {
    env::var("COMPUTE_DAEMON_URL").unwrap_or_else(|_| "http://127.0.0.1:9090".to_string())
}

pub(crate) fn compute_score_context(context: &NodeContext, task: &NetworkTask) -> BetaPosterior {
    let task_scale = if task.task_id.is_empty() {
        1.0
    } else {
        let hardware_hint = task.hardware_hint.unwrap_or(context.hardware);
        hardware_hint.similarity(context.hardware)
    };
    BetaPosterior::with_scale_hint(task_scale)
}

/// POSTs `payload` and parses the JSON answer; logs and returns `None` on
/// any failure (`label` names the call in the logs).
pub(crate) async fn post_json(
    client: &reqwest::Client,
    url: &str,
    payload: &serde_json::Value,
    label: &str,
) -> Option<serde_json::Value> {
    let response = match client.post(url).json(payload).send().await {
        Ok(response) => response,
        Err(e) => {
            println!(" {label} call failed: {e}");
            return None;
        }
    };
    match response.json().await {
        Ok(data) => Some(data),
        Err(e) => {
            println!(" {label} response parse failed: {e}");
            None
        }
    }
}

/// Best effort: reports the outcome to the reputation bridge.
pub(crate) async fn report_reputation(
    context: &NodeContext,
    client: &reqwest::Client,
    success: bool,
) {
    let reputation_url =
        env::var("REPUTATION_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:9091".to_string());
    let observe_payload = serde_json::json!({
        "peer_id": context.local_peer_id.to_string(),
        "success": success,
        "weight": 1.0
    });
    let url = format!("{reputation_url}/reputation/observe");
    if let Some(data) = post_json(client, &url, &observe_payload, "Reputation").await {
        println!(" Reputation updated: {:?}", data);
    }
}

pub(crate) fn log_affinity(context: &NodeContext, task: &NetworkTask) {
    let posterior = compute_score_context(context, task);
    let affinity_key =
        silicium_node_core::affinity::AffinityKey::new(context.hardware, task.task_id.clone());
    let affinity_record =
        silicium_node_core::affinity::AffinityRecord::new(affinity_key, posterior);
    let affinity_envelope = DhtRecordEnvelope::affinity(&affinity_record);
    println!(
        " Post-exec affinity record prepared for DHT key {}",
        affinity_envelope.key
    );
}
