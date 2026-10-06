//! Raytracer computation on the worker: optional runtime payload, render of
//! the tile by the compute daemon (`/compute`), local self-check of its
//! milestone commitment (`/verify`), reputation report. Also renders single
//! blocks for verifiers ([`render_region`]).

use crate::{
    processing::{
        NodeContext, compute_url, daemon_client, log_affinity, post_json, report_reputation,
    },
    task::NetworkTask,
    workload::ComputeOutcome,
};
use silicium_node_core::taskbook::{MAX_MILESTONES, MilestoneSample};
use std::time::Duration;

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
