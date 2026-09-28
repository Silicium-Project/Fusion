//! Data types shared by the Tauri commands, the supervisor and the update
//! logic (serialised to the frontend as camelCase JSON).

use crate::*;

#[derive(Default)]
pub(crate) struct ProcessState {
    pub(crate) node: Mutex<Option<Child>>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NodeConfig {
    pub(crate) repo_root: String,
    pub(crate) orchestrator_url: String,
    pub(crate) advertise_host: String,
    pub(crate) node_id: String,
    pub(crate) reputation_score: u16,
}

#[derive(Debug, Serialize)]
pub(crate) struct NodeStatus {
    pub(crate) running: bool,
    pub(crate) roles: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AppDefaults {
    pub(crate) repo_root: String,
    pub(crate) advertise_host: String,
    pub(crate) orchestrator_url: String,
    pub(crate) node_id: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct CheckItem {
    pub(crate) name: String,
    pub(crate) ok: bool,
    pub(crate) detail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NodeActivity {
    pub(crate) known_results: usize,
    pub(crate) known_tasks: usize,
    pub(crate) last_result: String,
    pub(crate) storage_bytes: u64,
    pub(crate) history: Vec<HistoryItem>,
    pub(crate) machines: Vec<MachineActivity>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct MachineActivity {
    pub(crate) node_id: String,
    pub(crate) identity_id: String,
    pub(crate) online: bool,
    pub(crate) self_node: bool,
    pub(crate) scheduler_active: bool,
    pub(crate) status: String,
    pub(crate) roles: Vec<String>,
    pub(crate) app_version: String,
    pub(crate) release_channel: String,
    pub(crate) release_build: String,
    pub(crate) http_base_url: String,
    pub(crate) mesh_post_url: String,
    pub(crate) relay_capable: bool,
    pub(crate) features: Vec<String>,
    pub(crate) candidates: Vec<MachineCandidate>,
    pub(crate) transport_attestations: Vec<TransportAttestation>,
    pub(crate) platform: String,
    pub(crate) cpu_count: u64,
    pub(crate) telemetry: RuntimeTelemetry,
    pub(crate) resource_reputation: Vec<BayesianResourceScore>,
    pub(crate) active_tasks: Vec<MachineTaskActivity>,
    pub(crate) task_queue: Vec<MachineQueueItem>,
    pub(crate) last_seen_unix: u64,
    pub(crate) last_seen_utc: String,
    pub(crate) last_claim_poll_utc: String,
    pub(crate) last_claim_error: String,
    pub(crate) last_response_ok: Option<bool>,
    pub(crate) last_response_item_id: String,
    pub(crate) last_response_utc: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct MachineCandidate {
    pub(crate) candidate_type: String,
    pub(crate) transport: String,
    pub(crate) ip: String,
    pub(crate) port: u64,
    pub(crate) internet_routable: bool,
    pub(crate) source: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct TransportAttestation {
    pub(crate) claim_hash: String,
    pub(crate) signature: String,
    pub(crate) route: String,
    pub(crate) transport_backend: String,
    pub(crate) proof_scope: String,
    pub(crate) remote_peer_id: String,
    pub(crate) session_id: String,
    pub(crate) task_id: String,
    pub(crate) content_id: String,
    pub(crate) size_bytes: u64,
    pub(crate) endpoint: String,
    pub(crate) relay_peer_id: String,
    pub(crate) peer_proof_verified: bool,
    pub(crate) success: bool,
    pub(crate) failure_reason: String,
    pub(crate) timestamp_unix: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct MachineTaskActivity {
    pub(crate) item_id: String,
    pub(crate) role: String,
    pub(crate) activity: String,
    pub(crate) workload: String,
    pub(crate) fragment_index: String,
    pub(crate) fragment_count: String,
    pub(crate) source_task_id: String,
    pub(crate) source_node_id: String,
    pub(crate) bounds: String,
    pub(crate) phase: String,
    pub(crate) progress_percent: f64,
    pub(crate) progress_source: String,
    pub(crate) elapsed_ms: u64,
    pub(crate) eta_seconds: f64,
    pub(crate) completed_units: f64,
    pub(crate) total_units: f64,
    pub(crate) unit: String,
    pub(crate) throughput_units_per_second: f64,
    pub(crate) worker_threads: u64,
    pub(crate) pixels_completed: u64,
    pub(crate) pixels_total: u64,
    pub(crate) input_bytes: u64,
    pub(crate) attempt: u64,
    pub(crate) max_retries: u64,
    pub(crate) priority: String,
    pub(crate) queued_utc: String,
    pub(crate) resource_usage: RuntimeTelemetry,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct MachineQueueItem {
    pub(crate) item_id: String,
    pub(crate) kind: String,
    pub(crate) role: String,
    pub(crate) activity: String,
    pub(crate) workload: String,
    pub(crate) fragment_index: String,
    pub(crate) fragment_count: String,
    pub(crate) source_task_id: String,
    pub(crate) source_node_id: String,
    pub(crate) status: String,
    pub(crate) priority: String,
    pub(crate) assigned_peer_id: String,
    pub(crate) origin_node_id: String,
    pub(crate) bounds: String,
    pub(crate) queued_utc: String,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct RuntimeTelemetry {
    pub(crate) sampled_unix: u64,
    pub(crate) sample_interval_ms: u64,
    pub(crate) node_uptime_seconds: f64,
    pub(crate) process_cpu_percent: f64,
    pub(crate) process_cpu_percent_one_core: f64,
    pub(crate) process_cpu_seconds: f64,
    pub(crate) process_rss_bytes: u64,
    pub(crate) process_peak_rss_bytes: u64,
    pub(crate) system_cpu_percent: f64,
    pub(crate) system_memory_total_bytes: u64,
    pub(crate) system_memory_available_bytes: u64,
    pub(crate) system_memory_used_bytes: u64,
    pub(crate) system_memory_percent: f64,
    pub(crate) logical_cpu_count: u64,
    pub(crate) python_thread_count: u64,
    pub(crate) load_average: Vec<f64>,
    pub(crate) storage_total_bytes: u64,
    pub(crate) storage_free_bytes: u64,
    pub(crate) storage_used_percent: f64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NodeDiagnostics {
    pub(crate) repo_root: String,
    pub(crate) silicium_cli: String,
    pub(crate) log_dir: String,
    pub(crate) node_pid: Option<u32>,
    pub(crate) supervisor_pid: Option<u32>,
    pub(crate) node_running: bool,
    pub(crate) supervisor_running: bool,
    pub(crate) port_ready: bool,
    pub(crate) orchestrator: CheckItem,
    pub(crate) openssl: CheckItem,
    pub(crate) python: CheckItem,
    pub(crate) log_tail: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct HistoryItem {
    pub(crate) name: String,
    pub(crate) modified_at: u64,
    pub(crate) size_bytes: u64,
    pub(crate) kind: String,
    pub(crate) item_id: String,
    pub(crate) role: String,
    pub(crate) activity: String,
    pub(crate) fragment_index: String,
    pub(crate) ok: Option<bool>,
    pub(crate) peer_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateStatus {
    pub(crate) current_version: String,
    pub(crate) current_channel: String,
    pub(crate) current_build: String,
    pub(crate) latest_version: String,
    #[serde(default)]
    pub(crate) latest_build: String,
    #[serde(default)]
    pub(crate) latest_content_id: String,
    pub(crate) state: String,
    pub(crate) update_available: bool,
    pub(crate) automatic: bool,
    pub(crate) last_checked_utc: String,
    pub(crate) error: String,
    pub(crate) check_interval_seconds: u64,
}

#[derive(Debug, Clone, Deserialize)]
pub(crate) struct UpdateRelease {
    pub(crate) version: String,
    #[serde(default)]
    pub(crate) build: String,
    #[serde(default)]
    pub(crate) channel: String,
    #[serde(default)]
    pub(crate) platform: String,
    pub(crate) url: String,
    pub(crate) sha256: String,
    #[serde(default)]
    pub(crate) content_id: String,
    #[serde(default)]
    pub(crate) signature: String,
    #[serde(default)]
    pub(crate) signing_key_id: String,
    #[serde(default)]
    pub(crate) size_bytes: u64,
    #[serde(default = "default_true")]
    pub(crate) auto_install: bool,
    #[serde(default)]
    pub(crate) check_interval_seconds: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateInstallFailure {
    pub(crate) content_id: String,
    pub(crate) version: String,
    pub(crate) build: String,
    pub(crate) error: String,
    pub(crate) failed_at_utc: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct BayesianResourceScore {
    pub(crate) dimension: String,
    pub(crate) mean: f64,
    pub(crate) lower_bound: f64,
    pub(crate) evidence: f64,
    pub(crate) short_term_mean: f64,
    pub(crate) long_term_mean: f64,
}

pub(crate) fn default_true() -> bool {
    true
}
