//! Processing of a task received from the network: runtime execution (when the
//! task carries one), then compute, verification and reputation calls to the
//! local daemons, each step recorded as a signed task-book event.

use crate::{storage::TaskBookState, task::NetworkTask};
use libp2p::PeerId;
use silicium_node_core::{
    beta::BetaPosterior,
    hardware::HardwareBucket,
    p2p::DhtRecordEnvelope,
    taskbook::{PayloadRef, TaskEvent, TaskEventBody},
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

pub(crate) async fn record_task_event(context: &NodeContext, task_id: &str, body: TaskEventBody) {
    match context.taskbook.append_signed(task_id, body) {
        Ok(event) => {
            if context.tx_events.send(event).await.is_err() {
                println!(" Task book event channel closed for {task_id}");
            }
        }
        Err(err) => println!(" Failed to persist task book event for {task_id}: {err}"),
    }
}

pub(crate) async fn process_task(context: NodeContext, task: NetworkTask) {
    record_task_event(
        &context,
        &task.task_id,
        TaskEventBody::ClaimProposed { attempt: 1 },
    )
    .await;

    let client = match daemon_client(context.compute_timeout_s) {
        Ok(client) => client,
        Err(error) => {
            println!(" Cannot build the daemon HTTP client: {error}");
            return;
        }
    };
    let compute_url =
        env::var("COMPUTE_DAEMON_URL").unwrap_or_else(|_| "http://127.0.0.1:9090".to_string());
    let reputation_url =
        env::var("REPUTATION_BRIDGE_URL").unwrap_or_else(|_| "http://127.0.0.1:9091".to_string());
    println!(
        "  Processing task {} from {}",
        task.task_id, context.local_peer_id
    );

    if let Some(runtime) = task.runtime_envelope(&context.local_peer_id.to_string()) {
        let runtime_kind = runtime.kind;
        let runtime_task_id = task.task_id.clone();
        let timeout_ms = runtime.limits.cpu_timeout_ms;
        match tokio::time::timeout(
            Duration::from_millis(timeout_ms),
            tokio::task::spawn_blocking(move || runtime.execute()),
        )
        .await
        {
            Ok(join_result) => match join_result {
                Ok(Ok(outcome)) => {
                    println!(
                        " Runtime {:?} completed for {} with exit code {}",
                        runtime_kind, runtime_task_id, outcome.exit_code
                    );
                }
                Ok(Err(err)) => {
                    println!(
                        " Runtime {:?} failed for {}: {err}",
                        runtime_kind, runtime_task_id
                    );
                    return;
                }
                Err(err) => {
                    println!(" Runtime task join failed for {}: {err}", runtime_task_id);
                    return;
                }
            },
            Err(_) => {
                println!(
                    " Runtime {:?} timed out for {}",
                    runtime_kind, runtime_task_id
                );
                return;
            }
        }
    } else {
        println!(
            "  Task {} has no executable runtime payload; using compute fallback",
            task.task_id
        );
    }

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

    let compute_res = match client
        .post(format!("{compute_url}/compute"))
        .json(&compute_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Compute call failed: {e}");
            return;
        }
    };

    let compute_data: serde_json::Value = match compute_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Compute response parse failed: {e}");
            return;
        }
    };

    let hash = match compute_data.get("hash").and_then(|v| v.as_str()) {
        Some(h) => h,
        None => {
            println!(" Compute failed: {:?}", compute_data);
            return;
        }
    };

    println!(" Compute successful. Hash: {}", hash);
    let result = PayloadRef {
        uri: format!("result://{}", task.task_id),
        sha256: TaskEvent::payload_hash(hash.as_bytes()),
    };
    record_task_event(
        &context,
        &task.task_id,
        TaskEventBody::ResultPublished { attempt: 1, result },
    )
    .await;

    // Check the tile against the milestone commitment returned by the
    // compute daemon (still a self-check: cross-verification by another peer
    // is not implemented in the Rust node yet).
    let Some(manifest) = compute_data.get("milestones").cloned() else {
        println!(
            " Compute response has no milestone commitment: {:?}",
            compute_data
        );
        return;
    };
    let verify_payload = serde_json::json!({
        "ppm_path": task.output_path,
        "manifest": manifest,
        "seed": task.seed,
        "reputation": 50.0
    });

    let verify_res = match client
        .post(format!("{compute_url}/verify"))
        .json(&verify_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Verify call failed: {e}");
            return;
        }
    };

    let verify_data: serde_json::Value = match verify_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Verify response parse failed: {e}");
            return;
        }
    };

    let success = verify_data
        .get("verified")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    println!(" Verify result: {}", success);
    // A self-check is not a verification: the task book only counts verdicts
    // from peers other than the claimant, so none is recorded here.

    let observe_payload = serde_json::json!({
        "peer_id": context.local_peer_id.to_string(),
        "success": success,
        "weight": 1.0
    });

    let rep_res = match client
        .post(format!("{reputation_url}/reputation/observe"))
        .json(&observe_payload)
        .send()
        .await
    {
        Ok(res) => res,
        Err(e) => {
            println!(" Reputation call failed: {e}");
            return;
        }
    };

    let rep_data: serde_json::Value = match rep_res.json().await {
        Ok(d) => d,
        Err(e) => {
            println!(" Reputation response parse failed: {e}");
            return;
        }
    };
    println!(" Reputation updated: {:?}", rep_data);

    let posterior = compute_score_context(&context, &task);
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
