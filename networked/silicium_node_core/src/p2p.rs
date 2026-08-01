use crate::{affinity::AffinityRecord, beta::BetaPosterior, hardware::HardwareBucket};
use serde::{Deserialize, Serialize};

pub const DHT_NAMESPACE: &str = "silicium";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DhtRecordKind {
    HardwareScore,
    TaskEnvelope,
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

    pub fn hardware_score(peer_id: &str, score: &BetaPosterior) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::HardwareScore,
            key: format!("{DHT_NAMESPACE}/hardware/v1/{peer_id}"),
            payload: score.to_bytes().expect("valid beta posterior"),
        }
    }

    pub fn task_envelope(task_id: &str, bytes: Vec<u8>) -> Self {
        Self {
            version: Self::VERSION,
            kind: DhtRecordKind::TaskEnvelope,
            key: format!("{DHT_NAMESPACE}/task/v1/{task_id}"),
            payload: bytes,
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
}

impl TaskEnvelope {
    pub fn to_dht_record(&self) -> DhtRecordEnvelope {
        DhtRecordEnvelope::task_envelope(
            &self.task_id,
            serde_json::to_vec(self).expect("task envelope serializes"),
        )
    }
}
