//! Task payload exchanged on the network: [`NetworkTask`] (what the HTTP API
//! and gossipsub carry) and [`GossipMessage`] (the gossipsub envelope).

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use silicium_node_core::{
    hardware::HardwareBucket,
    p2p::{ByteRange, Region, TaskEnvelope},
    taskbook::TaskEvent,
};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

/// Runtime profile exchanged on the authenticated gossipsub channel.
///
/// libp2p signs the enclosing message with the peer identity. The peer_id is
/// kept in the payload as well so the BackEnd can expose the human-readable
/// node id without losing the transport identity used for liveness checks.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct PeerProfile {
    pub(crate) node_id: String,
    pub(crate) peer_id: String,
    /// Author key used by the replicated task book; lets a splitter apply
    /// the same Bayesian reliability history to live compute peers in gossip.
    #[serde(default)]
    pub(crate) task_author: String,
    pub(crate) roles: Vec<String>,
    pub(crate) app_version: String,
    pub(crate) release_channel: String,
    pub(crate) release_build: String,
    #[serde(default)]
    pub(crate) capacity: Value,
    #[serde(default)]
    pub(crate) activity: Value,
    #[serde(default)]
    pub(crate) task_queue: Vec<Value>,
    pub(crate) last_seen_unix: i64,
    pub(crate) last_seen_utc: String,
}

/// Builds the local profile sent at startup and on the heartbeat cadence;
/// `active_tasks` is the work in progress (see [`crate::activity`]) and
/// `telemetry` the latest resource sample (see [`crate::telemetry`]).
pub(crate) fn local_peer_profile(
    peer_id: &str,
    task_author: &str,
    active_tasks: Vec<Value>,
    telemetry: Value,
) -> PeerProfile {
    let logical_cpu_count = std::thread::available_parallelism()
        .map(|value| value.get())
        .unwrap_or(1);
    PeerProfile {
        node_id: std::env::var("SILICIUM_NODE_ID")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| peer_id.to_string()),
        peer_id: peer_id.to_string(),
        task_author: task_author.to_string(),
        roles: std::env::var("SILICIUM_NODE_ROLES")
            .unwrap_or_else(|_| "compute,verify".to_string())
            .split(',')
            .map(str::trim)
            .filter(|role| !role.is_empty())
            .map(str::to_string)
            .collect(),
        app_version: std::env::var("SILICIUM_APP_VERSION")
            .unwrap_or_else(|_| "unknown".to_string()),
        release_channel: std::env::var("SILICIUM_RELEASE_CHANNEL")
            .unwrap_or_else(|_| "dev".to_string()),
        release_build: std::env::var("SILICIUM_RELEASE_BUILD")
            .unwrap_or_else(|_| "local".to_string()),
        // `ai_models`: models of the AI catalogue whose files are on this
        // node (the site prices a job lower when workers already have its
        // model).
        capacity: json!({
            "logical_cpu_count": logical_cpu_count,
            "ai_models": crate::workload::hf::warm_models(),
            // Models for which the Hub sent a file that is not the pinned
            // one (the BackEnd quarantines a model two nodes report).
            "ai_model_faults": crate::workload::hf::model_faults(),
            "supported_workloads": crate::workload::advertised_ids(),
        }),
        activity: json!({
            "status": if active_tasks.is_empty() { "idle" } else { "working" },
            "active_tasks": active_tasks,
            "telemetry": telemetry,
        }),
        task_queue: Vec::new(),
        last_seen_unix: unix_seconds(),
        last_seen_utc: utc_now(),
    }
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub(crate) struct NetworkTask {
    pub(crate) task_id: String,
    /// Business identifier carried with the envelope for job status grouping.
    #[serde(skip)]
    pub(crate) root_job_id: Option<String>,
    /// Parent task used to authorize recursive work from the accepted claimant.
    #[serde(skip)]
    pub(crate) parent_task_id: Option<String>,
    pub(crate) scene_path: String,
    pub(crate) output_path: String,
    pub(crate) seed: String,
    #[serde(default)]
    pub(crate) hardware_hint: Option<HardwareBucket>,
    #[serde(default)]
    pub(crate) runtime_hint: Option<String>,
    #[serde(default)]
    pub(crate) runtime_args: Vec<String>,
    #[serde(default)]
    pub(crate) runtime_env: BTreeMap<String, String>,
    #[serde(default)]
    pub(crate) runtime_workdir: Option<PathBuf>,
    #[serde(default)]
    pub(crate) runtime_module_path: Option<PathBuf>,
    #[serde(default)]
    pub(crate) runtime_image: Option<String>,
    /// SHA-256 of the scene file, set by the publisher (see [`crate::content`]).
    #[serde(default)]
    pub(crate) scene_sha256: Option<String>,
    /// Part of the image to render (a fragment of a job, see
    /// [`crate::jobs`]); the whole image when absent.
    #[serde(default)]
    pub(crate) region: Option<Region>,
    /// Workload of the task (see [`crate::workload`]); absent for tasks of
    /// older publishers, which are raytracer renders.
    #[serde(default)]
    pub(crate) workload: Option<String>,
    #[serde(default)]
    pub(crate) solana_payment: Option<silicium_node_core::p2p::SolanaPaymentRef>,
    /// Chunk of the input to process (workloads splitting a file).
    #[serde(default)]
    pub(crate) byte_range: Option<ByteRange>,
    #[serde(default)]
    pub(crate) delegation_depth: u8,
    /// Exact fragment count requested by the local BackEnd. This is a local
    /// publishing hint and is deliberately not sent to peers.
    #[serde(skip)]
    pub(crate) requested_fragment_count: Option<usize>,
}

impl From<TaskEnvelope> for NetworkTask {
    fn from(value: TaskEnvelope) -> Self {
        Self {
            task_id: value.task_id,
            root_job_id: value.root_job_id,
            parent_task_id: value.parent_task_id,
            scene_path: value.scene_path,
            output_path: value.output_path,
            seed: value.seed,
            hardware_hint: value.hardware_hint,
            runtime_hint: value.runtime_hint,
            runtime_args: value.runtime_args,
            runtime_env: value.runtime_env,
            runtime_workdir: value.runtime_workdir,
            runtime_module_path: value.runtime_module_path,
            runtime_image: value.runtime_image,
            scene_sha256: value.scene_sha256,
            region: value.region,
            workload: value.workload,
            solana_payment: value.solana_payment,
            byte_range: value.byte_range,
            delegation_depth: value.delegation_depth,
            requested_fragment_count: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub(crate) enum GossipMessage {
    Task(TaskEnvelope),
    TaskEvent(TaskEvent),
    PeerHeartbeat(PeerProfile),
    /// Asks peers for the task-book events of `author` after `after_sequence`.
    TaskEventsRequest {
        author: String,
        after_sequence: u64,
    },
}

fn unix_seconds() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default()
}

pub(crate) fn utc_now() -> String {
    let seconds = unix_seconds();
    let days = seconds.div_euclid(86_400);
    let day_seconds = seconds.rem_euclid(86_400);
    let hour = day_seconds / 3_600;
    let minute = (day_seconds % 3_600) / 60;
    let second = day_seconds % 60;
    let (year, month, day) = civil_date(days);
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

fn civil_date(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 }.div_euclid(146_097);
    let day_of_era = z - era * 146_097;
    let year_of_era = (day_of_era - day_of_era / 1_460 + day_of_era / 36_524
        - day_of_era / 146_096)
        .div_euclid(365);
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_part = (5 * day_of_year + 2).div_euclid(153);
    let day = day_of_year - (153 * month_part + 2).div_euclid(5) + 1;
    let month = month_part + if month_part < 10 { 3 } else { -9 };
    (year + i64::from(month <= 2), month, day)
}

impl From<NetworkTask> for TaskEnvelope {
    fn from(value: NetworkTask) -> Self {
        Self {
            task_id: value.task_id,
            root_job_id: value.root_job_id,
            parent_task_id: value.parent_task_id,
            scene_path: value.scene_path,
            output_path: value.output_path,
            seed: value.seed,
            hardware_hint: value.hardware_hint,
            runtime_hint: value.runtime_hint,
            runtime_args: value.runtime_args,
            runtime_env: value.runtime_env,
            runtime_workdir: value.runtime_workdir,
            runtime_module_path: value.runtime_module_path,
            runtime_image: value.runtime_image,
            scene_sha256: value.scene_sha256,
            region: value.region,
            workload: value.workload,
            solana_payment: value.solana_payment,
            byte_range: value.byte_range,
            delegation_depth: value.delegation_depth,
        }
    }
}

impl NetworkTask {
    pub(crate) fn runtime_envelope(
        &self,
        peer_id: &str,
    ) -> Option<silicium_node_core::runtime::RuntimeEnvelope> {
        let task: TaskEnvelope = self.clone().into();
        task.runtime_envelope(peer_id)
    }
}
