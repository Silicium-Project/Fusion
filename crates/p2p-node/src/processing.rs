//! Execution of a task this node was accepted for: runtime execution (when
//! the task carries one), then compute, self-check and reputation calls to
//! the local daemons. Task-book bookkeeping (claim, lease, result) is in
//! [`crate::worker`].

use crate::{storage::TaskBookState, task::NetworkTask};
use libp2p::PeerId;
use silicium_node_core::{
    beta::BetaPosterior, hardware::HardwareBucket, p2p::DhtRecordEnvelope, taskbook::TaskEvent,
};
use std::{env, time::Duration};
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

pub(crate) fn compute_score_context(context: &NodeContext, task: &NetworkTask) -> BetaPosterior {
    let task_scale = if task.task_id.is_empty() {
        1.0
    } else {
        let hardware_hint = task.hardware_hint.unwrap_or(context.hardware);
        hardware_hint.similarity(context.hardware)
    };
    BetaPosterior::with_scale_hint(task_scale)
}

/// Runs the task and returns the hash of a result that passed the local
/// milestone self-check, or `None` when anything failed (the caller then
/// releases the attempt).
pub(crate) async fn execute_task(context: &NodeContext, task: &NetworkTask) -> Option<String> {
    let client = daemon_client(context.compute_timeout_s)
        .map_err(|error| println!(" Cannot build the daemon HTTP client: {error}"))
        .ok()?;
    let compute_url =
        env::var("COMPUTE_DAEMON_URL").unwrap_or_else(|_| "http://127.0.0.1:9090".to_string());
    println!(
        "  Processing task {} from {}",
        task.task_id, context.local_peer_id
    );
    run_runtime(context, task).await?;

    // Both paths are relative to the compute daemon's work directory
    // (the task was sanitized on admission).
    let compute_payload = serde_json::json!({
        "scene_path": task.scene_path,
        "output_path": task.output_path,
        "y_start": null,
        "y_end": null,
        "x_start": null,
        "x_end": null
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
    verified.then(|| hash.to_string())
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
