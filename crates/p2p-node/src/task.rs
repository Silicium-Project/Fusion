//! Task payload exchanged on the network: [`NetworkTask`] (what the HTTP API
//! and gossipsub carry) and [`GossipMessage`] (the gossipsub envelope).

use serde::{Deserialize, Serialize};
use silicium_node_core::{
    hardware::HardwareBucket,
    p2p::{Region, TaskEnvelope},
    taskbook::TaskEvent,
};
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub(crate) struct NetworkTask {
    pub(crate) task_id: String,
    /// Business identifier kept by the local BackEnd compatibility layer.
    /// It is deliberately not sent to peers: the signed task id remains the
    /// authoritative network identifier.
    #[serde(skip)]
    pub(crate) root_job_id: Option<String>,
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
}

impl From<TaskEnvelope> for NetworkTask {
    fn from(value: TaskEnvelope) -> Self {
        Self {
            task_id: value.task_id,
            root_job_id: None,
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
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload")]
pub(crate) enum GossipMessage {
    Task(TaskEnvelope),
    TaskEvent(TaskEvent),
    /// Asks peers for the task-book events of `author` after `after_sequence`.
    TaskEventsRequest {
        author: String,
        after_sequence: u64,
    },
}

impl From<NetworkTask> for TaskEnvelope {
    fn from(value: NetworkTask) -> Self {
        Self {
            task_id: value.task_id,
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
