//! Execution of a task this node was accepted for: runtime execution (when
//! the task carries one), then compute, self-check and reputation calls to
//! the local daemons. Task-book bookkeeping (claim, lease, result) is in
//! [`crate::worker`].

use crate::{
    content::ContentStore,
    storage::TaskBookState,
    task::{NetworkTask, PeerProfile},
};
use libp2p::PeerId;
use silicium_node_core::{
    beta::BetaPosterior,
    hardware::HardwareBucket,
    p2p::DhtRecordEnvelope,
    taskbook::{MAX_MILESTONES, MilestoneSample, TaskEvent},
};
use std::{
    collections::BTreeMap,
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
    /// Upper bound of one compute call, in seconds.
    pub(crate) compute_timeout_s: u64,
    /// Tasks this node knows (received or published), by task id: what a
    /// verifier needs to re-render milestones.
    pub(crate) known_tasks: Arc<Mutex<BTreeMap<String, NetworkTask>>>,
    /// Scenes and result images shared with peers, inside the compute work
    /// directory.
    pub(crate) content: ContentStore,
    /// Peers currently connected (refreshed by the event loop).
    pub(crate) connected_peers: Arc<AtomicUsize>,
    /// Connected peers that can independently compute or verify a result.
    /// The orchestrator/storage peer is deliberately excluded from this
    /// count, so a single worker may use the configured self-verification
    /// fallback while remaining connected to the control plane.
    pub(crate) connected_workers: Arc<AtomicUsize>,
    /// Free compute slots: a worker claims a task only once it holds one.
    pub(crate) compute_slots: Arc<tokio::sync::Semaphore>,
}

impl NodeContext {
    /// True when this node has no connected peer.
    pub(crate) fn is_alone(&self) -> bool {
        self.connected_peers.load(Ordering::Relaxed) == 0
    }

    /// True when this node is the only compute/verification peer currently
    /// connected. The publisher/orchestrator itself is not a worker.
    pub(crate) fn is_only_worker(&self) -> bool {
        self.connected_workers.load(Ordering::Relaxed) == 0
    }

    /// Remembers a task for later verification.
    pub(crate) fn remember_task(&self, task: &NetworkTask) {
        if let Ok(mut known) = self.known_tasks.lock() {
            known.insert(task.task_id.clone(), task.clone());
        }
    }
}

/// Whether a peer profile represents a node that can independently compute or
/// verify a result. Control-plane roles such as `resource` and `storage` do
/// not count for the single-worker self-verification rule.
pub(crate) fn profile_is_worker(profile: &PeerProfile) -> bool {
    profile
        .roles
        .iter()
        .any(|role| {
            role.trim().eq_ignore_ascii_case("compute")
                || role.trim().eq_ignore_ascii_case("verify")
        })
}

#[cfg(test)]
mod tests {
    use super::{PeerProfile, profile_is_worker};
    use serde_json::json;

    fn profile(roles: &[&str]) -> PeerProfile {
        PeerProfile {
            node_id: "node".to_string(),
            peer_id: "peer".to_string(),
            roles: roles.iter().map(|role| (*role).to_string()).collect(),
            app_version: "test".to_string(),
            release_channel: "dev".to_string(),
            release_build: "test".to_string(),
            capacity: json!({}),
            activity: json!({}),
            task_queue: Vec::new(),
            last_seen_unix: 0,
            last_seen_utc: String::new(),
        }
    }

    #[test]
    fn control_plane_roles_do_not_count_as_workers() {
        assert!(!profile_is_worker(&profile(&["resource", "storage"])));
        assert!(profile_is_worker(&profile(&["compute", "verify"])));
        assert!(profile_is_worker(&profile(&[" VERIFY "])));
    }
}

/// A result that passed the local self-check, with its milestone commitment.
pub(crate) struct ComputeOutcome {
    pub(crate) milestones: Vec<MilestoneSample>,
}

/// HTTP client for the local daemons: every call is bounded in time, and the
/// compute daemon token (`SILICIUM_COMPUTE_TOKEN`) is sent when configured.
fn daemon_client(timeout_s: u64) -> Result<reqwest::Client, reqwest::Error> {
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

fn compute_url() -> String {
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

/// Runs the task and returns a result that passed the local milestone
/// self-check, or `None` when anything failed (the caller then releases the
/// attempt).
pub(crate) async fn execute_task(
    context: &NodeContext,
    task: &NetworkTask,
) -> Option<ComputeOutcome> {
    let client = daemon_client(context.compute_timeout_s)
        .map_err(|error| println!(" Cannot build the daemon HTTP client: {error}"))
        .ok()?;
    let compute_url = compute_url();
    println!(
        "  Processing task {} from {}",
        task.task_id, context.local_peer_id
    );
    run_runtime(context, task).await?;

    // Both paths are relative to the compute daemon's work directory
    // (the task was sanitized on admission).
    let region = task.region;
    let compute_payload = serde_json::json!({
        "scene_path": task.scene_path,
        "output_path": task.output_path,
        "y_start": region.map(|r| r.y_start),
        "y_end": region.map(|r| r.y_end),
        "x_start": region.map(|r| r.x_start),
        "x_end": region.map(|r| r.x_end),
    });
    let compute_data = post_json(
        &client,
        &format!("{compute_url}/compute"),
        &compute_payload,
        "Compute",
    )
    .await?;
    let Some(hash) = compute_data.get("hash").and_then(|v| v.as_str()) else {
        println!(" Compute failed: {:?}", compute_data);
        return None;
    };
    println!(" Compute successful. Hash: {}", hash);

    let verified = self_check(&client, &compute_url, task, &compute_data).await;
    report_reputation(context, &client, verified).await;
    log_affinity(context, task);
    let milestones = milestone_samples(&compute_data);
    verified.then_some(ComputeOutcome { milestones })
}

/// Milestone commitment of a compute answer, in the task book format.
fn milestone_samples(compute_data: &serde_json::Value) -> Vec<MilestoneSample> {
    let items = compute_data
        .get("milestones")
        .and_then(|manifest| manifest.get("milestones"))
        .and_then(|list| list.as_array())
        .cloned()
        .unwrap_or_default();
    let field = |item: &serde_json::Value, key: &str| {
        item.get(key)
            .and_then(|v| v.as_u64())
            .and_then(|v| u32::try_from(v).ok())
    };
    items
        .iter()
        .take(MAX_MILESTONES)
        .filter_map(|item| {
            Some(MilestoneSample {
                index: field(item, "index")?,
                x_start: field(item, "x_start")?,
                x_end: field(item, "x_end")?,
                y_start: field(item, "y_start")?,
                y_end: field(item, "y_end")?,
                pixel_sha256: item.get("pixel_sha256")?.as_str()?.to_string(),
            })
        })
        .collect()
}

/// Renders one block of rows of `task`'s scene into `output_path` (relative
/// to the compute daemon's work directory) and returns its pixel hash.
pub(crate) async fn render_region(
    context: &NodeContext,
    task: &NetworkTask,
    output_path: &str,
    region: &MilestoneSample,
) -> Option<String> {
    let client = daemon_client(context.compute_timeout_s)
        .map_err(|error| println!(" Cannot build the daemon HTTP client: {error}"))
        .ok()?;
    let payload = serde_json::json!({
        "scene_path": task.scene_path,
        "output_path": output_path,
        "y_start": region.y_start,
        "y_end": region.y_end,
        "x_start": region.x_start,
        "x_end": region.x_end,
        "batch_rows": region.y_end - region.y_start,
    });
    let data = post_json(
        &client,
        &format!("{}/compute", compute_url()),
        &payload,
        "Verify render",
    )
    .await?;
    data.get("hash")
        .and_then(|v| v.as_str())
        .map(str::to_string)
}

/// Executes the task's runtime payload, if any; `None` when it failed.
async fn run_runtime(context: &NodeContext, task: &NetworkTask) -> Option<()> {
    let Some(runtime) = task.runtime_envelope(&context.local_peer_id.to_string()) else {
        println!(
            "  Task {} has no executable runtime payload; using compute fallback",
            task.task_id
        );
        return Some(());
    };
    let runtime_kind = runtime.kind;
    let timeout_ms = runtime.limits.cpu_timeout_ms;
    let outcome = tokio::time::timeout(
        Duration::from_millis(timeout_ms),
        tokio::task::spawn_blocking(move || runtime.execute()),
    )
    .await;
    match outcome {
        Ok(Ok(Ok(outcome))) => {
            println!(
                " Runtime {:?} completed for {} with exit code {}",
                runtime_kind, task.task_id, outcome.exit_code
            );
            Some(())
        }
        Ok(Ok(Err(err))) => {
            println!(
                " Runtime {:?} failed for {}: {err}",
                runtime_kind, task.task_id
            );
            None
        }
        Ok(Err(err)) => {
            println!(" Runtime task join failed for {}: {err}", task.task_id);
            None
        }
        Err(_) => {
            println!(" Runtime {:?} timed out for {}", runtime_kind, task.task_id);
            None
        }
    }
}

/// POSTs `payload` and parses the JSON answer; logs and returns `None` on
/// any failure (`label` names the call in the logs).
async fn post_json(
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

/// Checks the tile against the milestone commitment returned by the compute
/// daemon. This is only a local self-check: verdicts that count in the task
/// book come from other peers.
async fn self_check(
    client: &reqwest::Client,
    compute_url: &str,
    task: &NetworkTask,
    compute_data: &serde_json::Value,
) -> bool {
    let Some(manifest) = compute_data.get("milestones").cloned() else {
        println!(
            " Compute response has no milestone commitment: {:?}",
            compute_data
        );
        return false;
    };
    let verify_payload = serde_json::json!({
        "ppm_path": task.output_path,
        "manifest": manifest,
        "seed": task.seed,
        "reputation": 50.0
    });
    let verified = post_json(
        client,
        &format!("{compute_url}/verify"),
        &verify_payload,
        "Verify",
    )
    .await
    .and_then(|data| data.get("verified").and_then(|v| v.as_bool()))
    .unwrap_or(false);
    println!(" Verify result: {}", verified);
    verified
}

/// Best effort: reports the outcome to the reputation bridge.
async fn report_reputation(context: &NodeContext, client: &reqwest::Client, success: bool) {
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

fn log_affinity(context: &NodeContext, task: &NetworkTask) {
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
