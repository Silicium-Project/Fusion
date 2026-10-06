//! Per-machine activity (candidates, queue, running tasks, telemetry,
//! reputation) parsed from the node exports.

use crate::*;

pub(crate) fn json_value_text(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(Value::Number(number)) => number.to_string(),
        Some(Value::Bool(boolean)) => boolean.to_string(),
        _ => String::new(),
    }
}

pub(crate) fn task_bounds(value: &Value) -> String {
    let x_start = json_value_text(value.get("x_start"));
    let x_end = json_value_text(value.get("x_end"));
    let y_start = json_value_text(value.get("y_start"));
    let y_end = json_value_text(value.get("y_end"));
    if [
        x_start.as_str(),
        x_end.as_str(),
        y_start.as_str(),
        y_end.as_str(),
    ]
    .iter()
    .any(|item| item.is_empty())
    {
        String::new()
    } else {
        format!("x {x_start}..{x_end}, y {y_start}..{y_end}")
    }
}

pub(crate) fn bayesian_number(value: Option<&Value>, key: &str) -> f64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
}

pub(crate) fn telemetry_number(value: Option<&Value>, key: &str) -> f64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_f64)
        .unwrap_or(0.0)
}

pub(crate) fn telemetry_u64(value: Option<&Value>, key: &str) -> u64 {
    value
        .and_then(|item| item.get(key))
        .and_then(Value::as_u64)
        .unwrap_or(0)
}

pub(crate) fn parse_runtime_telemetry(value: Option<&Value>) -> RuntimeTelemetry {
    RuntimeTelemetry {
        sampled_unix: telemetry_u64(value, "sampled_unix"),
        sample_interval_ms: telemetry_u64(value, "sample_interval_ms"),
        node_uptime_seconds: telemetry_number(value, "node_uptime_seconds"),
        process_cpu_percent: telemetry_number(value, "process_cpu_percent"),
        process_cpu_percent_one_core: telemetry_number(value, "process_cpu_percent_one_core"),
        process_cpu_seconds: telemetry_number(value, "process_cpu_seconds"),
        process_rss_bytes: telemetry_u64(value, "process_rss_bytes"),
        process_peak_rss_bytes: telemetry_u64(value, "process_peak_rss_bytes"),
        system_cpu_percent: telemetry_number(value, "system_cpu_percent"),
        system_memory_total_bytes: telemetry_u64(value, "system_memory_total_bytes"),
        system_memory_available_bytes: telemetry_u64(value, "system_memory_available_bytes"),
        system_memory_used_bytes: telemetry_u64(value, "system_memory_used_bytes"),
        system_memory_percent: telemetry_number(value, "system_memory_percent"),
        logical_cpu_count: telemetry_u64(value, "logical_cpu_count"),
        python_thread_count: telemetry_u64(value, "python_thread_count"),
        load_average: value
            .and_then(|item| item.get("load_average"))
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_f64)
            .collect(),
        storage_total_bytes: telemetry_u64(value, "storage_total_bytes"),
        storage_free_bytes: telemetry_u64(value, "storage_free_bytes"),
        storage_used_percent: telemetry_number(value, "storage_used_percent"),
    }
}

pub(crate) fn parse_resource_reputation(peer: &Value) -> Vec<BayesianResourceScore> {
    let dimensions = peer
        .get("resource_reputation")
        .and_then(|item| item.get("dimensions"))
        .and_then(Value::as_object);
    ["connection", "storage", "compute", "verify", "delegation"]
        .into_iter()
        .filter_map(|dimension| {
            let score = dimensions?.get(dimension)?;
            let combined = score.get("combined");
            Some(BayesianResourceScore {
                dimension: dimension.to_string(),
                mean: bayesian_number(combined, "mean"),
                lower_bound: bayesian_number(combined, "lower_bound"),
                evidence: bayesian_number(combined, "evidence"),
                short_term_mean: bayesian_number(score.get("short_term"), "mean"),
                long_term_mean: bayesian_number(score.get("long_term"), "mean"),
            })
        })
        .collect()
}

/// Peer snapshot of the node: `node.<node id>.peers.json` written by the Rust
/// node, else `mesh.discovery.json` of the former Python node.
fn peer_snapshot_path(export_dir: &Path) -> Option<PathBuf> {
    let rust = fs::read_dir(export_dir)
        .ok()?
        .flatten()
        .map(|entry| entry.path())
        .filter(|path| {
            path.file_name()
                .map(|name| name.to_string_lossy())
                .is_some_and(|name| name.starts_with("node.") && name.ends_with(".peers.json"))
        })
        .max_by_key(|path| fs::metadata(path).and_then(|meta| meta.modified()).ok());
    rust.or_else(|| Some(export_dir.join("mesh.discovery.json")))
}

pub(crate) fn collect_machine_activity(export_dir: &Path) -> Vec<MachineActivity> {
    let Some(snapshot_path) = peer_snapshot_path(export_dir) else {
        return Vec::new();
    };
    let Ok(raw) = fs::read_to_string(snapshot_path) else {
        return Vec::new();
    };
    let Ok(snapshot) = serde_json::from_str::<Value>(&raw) else {
        return Vec::new();
    };
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let mut machines = snapshot
        .get("peers")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|peer| {
            let node_id = peer.get("node_id")?.as_str()?.to_string();
            let last_seen = peer
                .get("last_seen_unix")
                .and_then(Value::as_u64)
                .unwrap_or(0);
            let last_claim_poll = peer
                .get("last_claim_poll_unix")
                .and_then(|value| {
                    value
                        .as_f64()
                        .or_else(|| value.as_u64().map(|item| item as f64))
                })
                .unwrap_or(0.0);
            let candidates = peer
                .get("candidates")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .map(|candidate| MachineCandidate {
                    candidate_type: candidate
                        .get("candidate_type")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    transport: candidate
                        .get("transport")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    ip: candidate
                        .get("ip")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                    port: candidate.get("port").and_then(Value::as_u64).unwrap_or(0),
                    internet_routable: candidate
                        .get("internet_routable")
                        .and_then(Value::as_bool)
                        .unwrap_or(false),
                    source: candidate
                        .get("source")
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string(),
                })
                .collect::<Vec<_>>();
            let transport_attestations = peer
                .get("transport_attestations")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|attestation| {
                    Some(TransportAttestation {
                        claim_hash: attestation.get("claim_hash")?.as_str()?.to_string(),
                        signature: attestation
                            .get("signature")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        route: attestation
                            .get("route")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        transport_backend: attestation
                            .get("transport_backend")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        proof_scope: attestation
                            .get("proof_scope")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        remote_peer_id: attestation
                            .get("remote_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        session_id: attestation
                            .get("session_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        task_id: attestation
                            .get("task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        content_id: attestation
                            .get("content_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        size_bytes: attestation
                            .get("size_bytes")
                            .and_then(Value::as_u64)
                            .unwrap_or(0),
                        endpoint: attestation
                            .get("endpoint")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        relay_peer_id: attestation
                            .get("relay_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        peer_proof_verified: attestation
                            .get("peer_proof_verified")
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        success: attestation
                            .get("success")
                            .and_then(Value::as_bool)
                            .unwrap_or(false),
                        failure_reason: attestation
                            .get("failure_reason")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        timestamp_unix: attestation
                            .get("timestamp_unix")
                            .and_then(Value::as_u64)
                            .unwrap_or(0),
                    })
                })
                .collect::<Vec<_>>();
            let capacity = peer.get("capacity").and_then(Value::as_object);
            let activity = peer.get("activity").and_then(Value::as_object);
            let active_tasks = activity
                .and_then(|item| item.get("active_tasks"))
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|task| {
                    Some(MachineTaskActivity {
                        item_id: task.get("item_id")?.as_str()?.to_string(),
                        role: task
                            .get("role")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        activity: task
                            .get("activity")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        workload: task
                            .get("workload")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        fragment_index: json_value_text(task.get("fragment_index")),
                        fragment_count: json_value_text(task.get("fragment_count")),
                        source_task_id: task
                            .get("source_task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        source_node_id: task
                            .get("source_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        bounds: task_bounds(task),
                        phase: task
                            .get("phase")
                            .and_then(Value::as_str)
                            .unwrap_or("executing")
                            .to_string(),
                        progress_percent: telemetry_number(Some(task), "progress_percent"),
                        progress_source: task
                            .get("progress_source")
                            .and_then(Value::as_str)
                            .unwrap_or("unknown")
                            .to_string(),
                        elapsed_ms: telemetry_u64(Some(task), "elapsed_ms"),
                        eta_seconds: telemetry_number(Some(task), "eta_seconds"),
                        completed_units: telemetry_number(Some(task), "completed_units"),
                        total_units: telemetry_number(Some(task), "total_units"),
                        unit: task
                            .get("unit")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        throughput_units_per_second: telemetry_number(
                            Some(task),
                            "throughput_units_per_second",
                        ),
                        worker_threads: telemetry_u64(Some(task), "worker_threads"),
                        pixels_completed: telemetry_u64(Some(task), "pixels_completed"),
                        pixels_total: telemetry_u64(Some(task), "pixels_total"),
                        input_bytes: telemetry_u64(Some(task), "input_bytes"),
                        attempt: telemetry_u64(Some(task), "attempt"),
                        max_retries: telemetry_u64(Some(task), "max_retries"),
                        priority: task
                            .get("priority")
                            .and_then(Value::as_str)
                            .unwrap_or("normal")
                            .to_string(),
                        queued_utc: task
                            .get("queued_utc")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        resource_usage: parse_runtime_telemetry(task.get("resource_usage")),
                    })
                })
                .collect::<Vec<_>>();
            let task_queue = peer
                .get("task_queue")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|task| {
                    Some(MachineQueueItem {
                        item_id: task.get("item_id")?.as_str()?.to_string(),
                        kind: task
                            .get("kind")
                            .and_then(Value::as_str)
                            .unwrap_or("task")
                            .to_string(),
                        role: task
                            .get("role")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        activity: task
                            .get("activity")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        workload: task
                            .get("workload")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        fragment_index: json_value_text(task.get("fragment_index")),
                        fragment_count: json_value_text(task.get("fragment_count")),
                        source_task_id: task
                            .get("source_task_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        source_node_id: task
                            .get("source_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        status: task
                            .get("status")
                            .and_then(Value::as_str)
                            .unwrap_or("queued")
                            .to_string(),
                        priority: task
                            .get("priority")
                            .and_then(Value::as_str)
                            .unwrap_or("normal")
                            .to_string(),
                        assigned_peer_id: task
                            .get("assigned_peer_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        origin_node_id: task
                            .get("origin_node_id")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                        bounds: task_bounds(task),
                        queued_utc: task
                            .get("queued_utc")
                            .and_then(Value::as_str)
                            .unwrap_or("")
                            .to_string(),
                    })
                })
                .collect::<Vec<_>>();
            let last_response = activity
                .and_then(|item| item.get("last_response"))
                .and_then(Value::as_object);
            Some(MachineActivity {
                node_id,
                identity_id: peer
                    .get("identity_id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                online: last_seen > 0 && now.saturating_sub(last_seen) <= 45,
                self_node: peer.get("self").and_then(Value::as_bool).unwrap_or(false),
                scheduler_active: last_claim_poll > 0.0
                    && (now as f64 - last_claim_poll).max(0.0) <= 10.0,
                status: activity
                    .and_then(|item| item.get("status"))
                    .and_then(Value::as_str)
                    .unwrap_or(if active_tasks.is_empty() {
                        "idle"
                    } else {
                        "working"
                    })
                    .to_string(),
                roles: peer
                    .get("roles")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                app_version: peer
                    .get("app_version")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                release_channel: peer
                    .get("release_channel")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                release_build: peer
                    .get("release_build")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                http_base_url: peer
                    .get("http_base_url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                mesh_post_url: peer
                    .get("mesh_post_url")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                relay_capable: peer
                    .get("relay_capable")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
                features: peer
                    .get("features")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect(),
                candidates,
                transport_attestations,
                platform: capacity
                    .and_then(|item| item.get("platform"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                cpu_count: capacity
                    .and_then(|item| item.get("cpu_count"))
                    .and_then(Value::as_u64)
                    .unwrap_or(0),
                telemetry: parse_runtime_telemetry(
                    activity
                        .and_then(|item| item.get("telemetry"))
                        .or_else(|| peer.get("telemetry")),
                ),
                resource_reputation: parse_resource_reputation(peer),
                active_tasks,
                task_queue,
                last_seen_unix: last_seen,
                last_seen_utc: peer
                    .get("updated_utc")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_claim_poll_utc: peer
                    .get("last_claim_poll_utc")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_claim_error: peer
                    .get("last_claim_error")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_response_ok: last_response
                    .and_then(|item| item.get("ok"))
                    .and_then(Value::as_bool),
                last_response_item_id: last_response
                    .and_then(|item| item.get("item_id"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                last_response_utc: last_response
                    .and_then(|item| item.get("timestamp_utc"))
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            })
        })
        .collect::<Vec<_>>();
    machines.sort_by(|left, right| {
        right
            .online
            .cmp(&left.online)
            .then_with(|| left.node_id.cmp(&right.node_id))
    });
    machines
}
