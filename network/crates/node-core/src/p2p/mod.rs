//! Wire envelopes shared between peers: tasks and DHT records.
//!
//! A task received from another peer is untrusted: pass it through
//! [`TaskEnvelope::sanitize_remote`] before using it. That drops the runtime
//! fields a peer must not control (Docker image, working directory,
//! environment, output path) and refuses paths that leave the node's sandbox.

pub use crate::region::{ByteRange, Region};
use crate::{
    affinity::AffinityRecord,
    beta::BetaPosterior,
    hardware::HardwareBucket,
    runtime::{RuntimeEnvelope, RuntimeKind},
    taskbook::TaskEvent,
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::PathBuf};

pub const DHT_NAMESPACE: &str = "silicium";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DhtRecordKind {
    HardwareScore,
    TaskEnvelope,
    TaskEvent,
    AffinityPosterior,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DhtRecordEnvelope {
    pub version: u8,
    pub kind: DhtRecordKind,
    pub key: String,
    pub payload: Vec<u8>,
}

impl DhtRecordEnvelope {
    pub const VERSION: u8 = 1;

    pub fn hardware_record_key(peer_id: &str) -> String {
        format!("{DHT_NAMESPACE}/hardware/v1/{peer_id}")
    }

    pub fn task_record_key(task_id: &str) -> String {
        format!("{DHT_NAMESPACE}/task/v1/{task_id}")
    }

    pub fn task_event_key(event_hash: &str) -> String {
        format!("{DHT_NAMESPACE}/taskbook/v1/{event_hash}")
    }

    pub fn hardware_score(peer_id: &str, score: &BetaPosterior) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::HardwareScore,
            key: Self::hardware_record_key(peer_id),
            payload: score.to_bytes().expect("valid beta posterior"),
        }
    }

    pub fn task_envelope(task_id: &str, bytes: Vec<u8>) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::TaskEnvelope,
            key: Self::task_record_key(task_id),
            payload: bytes,
        }
    }

    pub fn task_event(event: &TaskEvent) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::TaskEvent,
            key: Self::task_event_key(&event.event_hash()),
            payload: serde_json::to_vec(event).expect("task event serializes"),
        }
    }

    pub fn affinity(record: &AffinityRecord) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::AffinityPosterior,
            key: record.key.to_record_key(),
            payload: record.posterior.to_bytes().expect("valid beta posterior"),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct HardwareNodeDescriptor {
    pub peer_id: String,
    pub bucket: HardwareBucket,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TaskEnvelope {
    pub task_id: String,
    /// Business identifier used for status and result aggregation.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub root_job_id: Option<String>,
    /// Parent fragment, present on tasks recursively delegated by a worker.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_task_id: Option<String>,
    pub scene_path: String,
    pub output_path: String,
    pub seed: String,
    #[serde(default)]
    pub hardware_hint: Option<HardwareBucket>,
    #[serde(default)]
    pub runtime_hint: Option<String>,
    #[serde(default)]
    pub runtime_args: Vec<String>,
    #[serde(default)]
    pub runtime_env: BTreeMap<String, String>,
    #[serde(default)]
    pub runtime_workdir: Option<PathBuf>,
    #[serde(default)]
    pub runtime_module_path: Option<PathBuf>,
    #[serde(default)]
    pub runtime_image: Option<String>,
    /// SHA-256 of the scene file: peers that lack it fetch it by this hash.
    #[serde(default)]
    pub scene_sha256: Option<String>,
    /// Part of the image to render (a fragment of a job); the whole image
    /// when absent.
    #[serde(default)]
    pub region: Option<Region>,
    /// Workload identifier (`raytracer`, `calcul/integrity/sha256`, ...);
    /// absent for tasks of older publishers, which are raytracer renders.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub workload: Option<String>,
    /// Public Solana escrow reference for an explicitly paid Devnet task.
    /// The worker still verifies every account and state against the program
    /// before signing a settlement transaction.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub solana_payment: Option<SolanaPaymentRef>,
    /// Part of the input to process, for workloads that split a file into
    /// byte chunks; the whole input when absent.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub byte_range: Option<ByteRange>,
    /// Number of network-selected split levels below the initial pre-split.
    #[serde(default)]
    pub delegation_depth: u8,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SolanaPaymentRef {
    pub job: String,
    pub expected_fragments: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fragment_index: Option<u32>,
}

/// What a node accepts from tasks published by other peers.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RemoteTaskPolicy {
    /// Allow a remote task to run a WASM module (resolved inside the node's
    /// sandbox). OCI images are never accepted from the network.
    pub allow_wasm: bool,
}

/// Why a remote task was refused.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum RemoteTaskError {
    #[error("remote_task_id_invalid")]
    InvalidTaskId,
    #[error("remote_task_path_invalid:{0}")]
    InvalidPath(String),
    #[error("remote_task_oci_refused")]
    OciRefused,
    #[error("remote_task_region_invalid")]
    InvalidRegion,
    #[error("remote_task_wasm_refused")]
    WasmRefused,
    #[error("remote_task_workload_invalid")]
    InvalidWorkload,
    #[error("remote_task_byte_range_invalid")]
    InvalidByteRange,
    #[error("remote_task_delegation_lineage_invalid")]
    InvalidDelegationLineage,
}

/// Longest workload identifier accepted from a peer.
pub const MAX_WORKLOAD_ID_LEN: usize = 80;

/// True for a well-formed workload identifier: lowercase letters, digits and
/// `/ . _ -`, at most [`MAX_WORKLOAD_ID_LEN`] characters. Whether the node
/// knows the workload is decided by the node itself.
pub fn is_valid_workload_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_WORKLOAD_ID_LEN
        && id.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"/._-".contains(&byte)
        })
        && !id
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
}

impl TaskEnvelope {
    /// Relative output path used for a raytracer task, whatever the
    /// publisher asked for.
    pub fn local_output_path(task_id: &str) -> Option<String> {
        Self::local_output_path_for(task_id, None)
    }

    /// Relative output path of a task of `workload`: `<task id>/output.ppm`
    /// for a raytracer render, `<task id>/output.bin` otherwise.
    pub fn local_output_path_for(task_id: &str, workload: Option<&str>) -> Option<String> {
        let extension = match workload {
            None | Some("raytracer") => "ppm",
            Some(_) => "bin",
        };
        crate::sandbox::safe_component(task_id).map(|id| format!("{id}/output.{extension}"))
    }

    /// Returns a copy that is safe to execute locally, or why the task must be
    /// dropped. Paths stay relative; resolve them with [`crate::sandbox::resolve`].
    pub fn sanitize_remote(
        &self,
        policy: &RemoteTaskPolicy,
    ) -> Result<TaskEnvelope, RemoteTaskError> {
        let task_id = self.task_id.trim();
        if task_id.is_empty()
            || task_id.len() > 128
            || crate::sandbox::safe_component(task_id).as_deref() != Some(task_id)
        {
            return Err(RemoteTaskError::InvalidTaskId);
        }
        let root_job_id = self
            .root_job_id
            .as_deref()
            .map(str::trim)
            .filter(|root| !root.is_empty())
            .map(str::to_string);
        if root_job_id
            .as_deref()
            .is_some_and(|root| root.len() > 128 || root.chars().any(char::is_control))
        {
            return Err(RemoteTaskError::InvalidDelegationLineage);
        }
        let parent_task_id = match self.parent_task_id.as_deref().map(str::trim) {
            Some(parent)
                if !parent.is_empty() && crate::taskbook::TaskEvent::is_valid_task_id(parent) =>
            {
                Some(parent.to_string())
            }
            Some(_) => return Err(RemoteTaskError::InvalidDelegationLineage),
            None => None,
        };
        if parent_task_id.is_some() != (self.delegation_depth > 0) {
            return Err(RemoteTaskError::InvalidDelegationLineage);
        }
        let workload = match self.workload.as_deref().map(str::trim) {
            None | Some("") => None,
            Some(id) if is_valid_workload_id(id) => Some(id.to_string()),
            Some(_) => return Err(RemoteTaskError::InvalidWorkload),
        };
        let probe = std::path::Path::new("/sandbox");
        crate::sandbox::resolve(probe, &self.scene_path)
            .map_err(|error| RemoteTaskError::InvalidPath(error.to_string()))?;
        if self.runtime_image.is_some()
            || self
                .runtime_hint
                .as_deref()
                .is_some_and(|hint| hint.eq_ignore_ascii_case("oci"))
        {
            return Err(RemoteTaskError::OciRefused);
        }
        let module_path = match &self.runtime_module_path {
            None => None,
            Some(_) if !policy.allow_wasm => return Err(RemoteTaskError::WasmRefused),
            Some(path) => {
                let text = path.to_string_lossy().to_string();
                crate::sandbox::resolve(probe, &text)
                    .map_err(|error| RemoteTaskError::InvalidPath(error.to_string()))?;
                Some(PathBuf::from(text))
            }
        };
        Ok(TaskEnvelope {
            task_id: task_id.to_string(),
            root_job_id,
            parent_task_id,
            scene_path: self.scene_path.trim().to_string(),
            output_path: Self::local_output_path_for(task_id, workload.as_deref())
                .ok_or(RemoteTaskError::InvalidTaskId)?,
            seed: self.seed.clone(),
            hardware_hint: self.hardware_hint,
            runtime_hint: module_path.as_ref().map(|_| "wasm".to_string()),
            runtime_args: if module_path.is_some() {
                self.runtime_args.clone()
            } else {
                Vec::new()
            },
            runtime_env: BTreeMap::new(),
            runtime_workdir: None,
            runtime_module_path: module_path,
            runtime_image: None,
            scene_sha256: self
                .scene_sha256
                .clone()
                .filter(|hash| hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit())),
            region: match self.region {
                Some(region) if !region.is_valid() => return Err(RemoteTaskError::InvalidRegion),
                region => region,
            },
            workload,
            solana_payment: self.solana_payment.clone(),
            byte_range: match self.byte_range {
                Some(range) if !range.is_valid() => return Err(RemoteTaskError::InvalidByteRange),
                range => range,
            },
            delegation_depth: self.delegation_depth,
        })
    }

    pub fn runtime_envelope(&self, peer_id: &str) -> Option<RuntimeEnvelope> {
        let kind = match self.runtime_hint.as_deref() {
            Some(hint) if hint.eq_ignore_ascii_case("oci") => RuntimeKind::Oci,
            Some(hint) if hint.eq_ignore_ascii_case("wasm") => RuntimeKind::Wasm,
            _ if self.runtime_image.is_some() => RuntimeKind::Oci,
            _ => RuntimeKind::Wasm,
        };

        if matches!(kind, RuntimeKind::Wasm) && self.runtime_module_path.is_none() {
            return None;
        }

        if matches!(kind, RuntimeKind::Oci) && self.runtime_image.is_none() {
            return None;
        }

        let mut runtime = match kind {
            RuntimeKind::Wasm => RuntimeEnvelope::wasm(self.runtime_args.clone())
                .with_module_path(self.runtime_module_path.clone().expect("module path")),
            RuntimeKind::Oci => RuntimeEnvelope::oci(self.runtime_args.clone())
                .with_image(self.runtime_image.clone().expect("image")),
        };

        runtime
            .env
            .insert("SILICIUM_TASK_ID".to_string(), self.task_id.clone());
        runtime
            .env
            .insert("SILICIUM_SCENE_PATH".to_string(), self.scene_path.clone());
        runtime
            .env
            .insert("SILICIUM_OUTPUT_PATH".to_string(), self.output_path.clone());
        runtime
            .env
            .insert("SILICIUM_SEED".to_string(), self.seed.clone());
        runtime
            .env
            .insert("SILICIUM_PEER_ID".to_string(), peer_id.to_string());
        runtime.env.extend(self.runtime_env.clone());
        runtime.working_dir = self.runtime_workdir.clone();
        Some(runtime)
    }

    pub fn to_dht_record(&self) -> DhtRecordEnvelope {
        DhtRecordEnvelope::task_envelope(
            &self.task_id,
            serde_json::to_vec(self).expect("task envelope serializes"),
        )
    }
}

#[cfg(test)]
mod tests;
