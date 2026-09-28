//! Processing of a task received from the network: runtime execution (when the
//! task carries one), then compute, verification and reputation calls to the
//! local daemons, each step recorded as a signed task-book event.

use crate::{storage::TaskBookState, task::NetworkTask};
use libp2p::PeerId;
use silicium_node_core::{
    beta::BetaPosterior,
    hardware::HardwareBucket,
    p2p::{DhtRecordEnvelope, TaskEnvelope},
    taskbook::{TaskEvent, TaskEventKind},
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

pub(crate) async fn record_task_event(
    context: &NodeContext,
    kind: TaskEventKind,
    task_id: &str,
    payload_ref: impl Into<String>,
    payload_hash: impl Into<String>,
) {
    match context
        .taskbook
        .append_signed(kind, task_id, payload_ref, payload_hash)
    {
        Ok(event) => {
            if context.tx_events.send(event).await.is_err() {
                println!(" Task book event channel closed for {task_id}");
            }
        }
        Err(err) => println!(" Failed to persist task book event for {task_id}: {err}"),
    }
}

pub(crate) async fn process_task(context: NodeContext, task: NetworkTask) {
    let task_bytes =
        serde_json::to_vec(&TaskEnvelope::from(task.clone())).expect("task envelope serializes");
    let task_payload_hash = TaskEvent::payload_hash(&task_bytes);
    record_task_event(
        &context,
        TaskEventKind::ClaimProposed,
        &task.task_id,
        DhtRecordEnvelope::task_record_key(&task.task_id),
        task_payload_hash,
    )
    .await;

    let client = reqwest::Client::new();
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
    record_task_event(
        &context,
        TaskEventKind::ResultPublished,
        &task.task_id,
        format!("result://{}", task.task_id),
        TaskEvent::payload_hash(hash.as_bytes()),
    )
    .await;

    let verify_payload = serde_json::json!({
        "ppm_path": task.output_path,
        "manifest": {
            "milestone_count": 1,
            "milestones": [
                {
                    "index": 0,
                    "y_start": 0,
                    "y_end": 2,
                    "pixel_sha256": hash
                }
            ]
        },
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
    record_task_event(
        &context,
        TaskEventKind::VerificationPublished,
        &task.task_id,
        format!("verification://{}", task.task_id),
        TaskEvent::payload_hash(success.to_string().as_bytes()),
    )
    .await;

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
