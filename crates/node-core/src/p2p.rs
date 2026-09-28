//! Wire envelopes shared between peers: tasks and DHT records.
//!
//! WARNING: `TaskEnvelope::runtime_envelope` trusts runtime fields received from
//! the network (image, working directory, environment). They must be validated
//! against an allow-list before this is used outside of tests.

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

impl TaskEnvelope {
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
}
