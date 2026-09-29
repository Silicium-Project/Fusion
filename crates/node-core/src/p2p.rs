//! Wire envelopes shared between peers: tasks and DHT records.
//!
//! A task received from another peer is untrusted: pass it through
//! [`TaskEnvelope::sanitize_remote`] before using it. That drops the runtime
//! fields a peer must not control (Docker image, working directory,
//! environment, output path) and refuses paths that leave the node's sandbox.

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
    #[error("remote_task_wasm_refused")]
    WasmRefused,
}

impl TaskEnvelope {
    /// Relative output path used for a task, whatever the publisher asked for.
    pub fn local_output_path(task_id: &str) -> Option<String> {
        crate::sandbox::safe_component(task_id).map(|id| format!("{id}/output.ppm"))
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
            scene_path: self.scene_path.trim().to_string(),
            output_path: Self::local_output_path(task_id).ok_or(RemoteTaskError::InvalidTaskId)?,
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
mod tests {
    use super::*;

    #[test]
    fn hardware_record_key_is_versioned() {
        assert_eq!(
            DhtRecordEnvelope::hardware_record_key("peer-123"),
            "silicium/hardware/v1/peer-123"
        );
    }

    #[test]
    fn task_record_key_is_versioned() {
        assert_eq!(
            DhtRecordEnvelope::task_record_key("task-456"),
            "silicium/task/v1/task-456"
        );
    }

    #[test]
    fn task_event_record_key_is_content_addressed() {
        let key = DhtRecordEnvelope::task_event_key(&"a".repeat(64));
        assert_eq!(key, format!("silicium/taskbook/v1/{}", "a".repeat(64)));
    }

    fn remote_task() -> TaskEnvelope {
        TaskEnvelope {
            task_id: "job-1-frag-000".to_string(),
            scene_path: "scenes/demo.cfg".to_string(),
            output_path: "/etc/passwd".to_string(),
            seed: "7".to_string(),
            hardware_hint: None,
            runtime_hint: None,
            runtime_args: vec!["--flag".to_string()],
            runtime_env: BTreeMap::from([("LD_PRELOAD".to_string(), "/tmp/evil.so".to_string())]),
            runtime_workdir: Some(PathBuf::from("/")),
            runtime_module_path: None,
            runtime_image: None,
        }
    }

    #[test]
    fn remote_tasks_lose_the_fields_a_peer_must_not_control() {
        let clean = remote_task()
            .sanitize_remote(&RemoteTaskPolicy::default())
            .unwrap();
        assert_eq!(clean.output_path, "job-1-frag-000/output.ppm");
        assert!(clean.runtime_env.is_empty());
        assert!(clean.runtime_workdir.is_none());
        assert!(clean.runtime_args.is_empty());
        assert!(clean.runtime_envelope("peer").is_none());
    }

    #[test]
    fn remote_tasks_cannot_pick_host_paths_or_docker_images() {
        let policy = RemoteTaskPolicy::default();
        for scene in ["../secret.cfg", "/etc/passwd", "C:\\Windows\\win.ini", ""] {
            let task = TaskEnvelope {
                scene_path: scene.to_string(),
                ..remote_task()
            };
            assert!(
                matches!(
                    task.sanitize_remote(&policy),
                    Err(RemoteTaskError::InvalidPath(_))
                ),
                "{scene}"
            );
        }
        let docker = TaskEnvelope {
            runtime_image: Some("evil:latest".to_string()),
            ..remote_task()
        };
        assert_eq!(
            docker.sanitize_remote(&policy),
            Err(RemoteTaskError::OciRefused)
        );
        let bad_id = TaskEnvelope {
            task_id: "../x".to_string(),
            ..remote_task()
        };
        assert_eq!(
            bad_id.sanitize_remote(&policy),
            Err(RemoteTaskError::InvalidTaskId)
        );
    }

    #[test]
    fn remote_wasm_needs_an_explicit_policy_and_a_sandboxed_module() {
        let wasm = TaskEnvelope {
            runtime_module_path: Some(PathBuf::from("modules/job.wasm")),
            ..remote_task()
        };
        assert_eq!(
            wasm.sanitize_remote(&RemoteTaskPolicy::default()),
            Err(RemoteTaskError::WasmRefused)
        );
        let allowed = wasm
            .sanitize_remote(&RemoteTaskPolicy { allow_wasm: true })
            .unwrap();
        assert_eq!(allowed.runtime_hint.as_deref(), Some("wasm"));
        assert!(allowed.runtime_env.is_empty());
        let escaping = TaskEnvelope {
            runtime_module_path: Some(PathBuf::from("../x.wasm")),
            ..remote_task()
        };
        assert!(
            escaping
                .sanitize_remote(&RemoteTaskPolicy { allow_wasm: true })
                .is_err()
        );
    }
}
