//! Picks the node that should run a task by sampling each candidate's posterior.

use crate::{
    affinity::{AffinityKey, AffinityRecord, TaskScale, sparse_affinity_prior},
    beta::BetaPosterior,
    hardware::HardwareBucket,
};
use rand::{SeedableRng, rngs::StdRng};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DispatchCandidate {
    pub peer_id: String,
    pub hardware: HardwareBucket,
    pub task_key: AffinityKey,
    pub posterior: BetaPosterior,
}

#[derive(Debug, Clone, PartialEq)]
pub struct DispatchDecision {
    pub peer_id: String,
    pub sampled_score: f64,
    pub affinity_score: f64,
}

#[derive(Debug, Default)]
pub struct Dispatcher {
    seed: u64,
}

impl Dispatcher {
    pub fn with_seed(seed: u64) -> Self {
        Self { seed }
    }

    pub fn select(&self, candidates: &[DispatchCandidate]) -> Option<DispatchDecision> {
        let mut rng = StdRng::seed_from_u64(self.seed);
        candidates
            .iter()
            .map(|candidate| {
                let sampled = candidate.posterior.sample(&mut rng);
                let affinity = candidate.hardware.similarity(candidate.task_key.hardware);
                DispatchDecision {
                    peer_id: candidate.peer_id.clone(),
                    sampled_score: sampled,
                    affinity_score: affinity,
                }
            })
            .max_by(|left, right| {
                (left.sampled_score * left.affinity_score)
                    .partial_cmp(&(right.sampled_score * right.affinity_score))
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
    }

    pub fn fallback_record(
        &self,
        hardware: HardwareBucket,
        task: impl Into<String>,
        scale: TaskScale,
    ) -> AffinityRecord {
        let key = AffinityKey::new(hardware, task);
        let posterior = sparse_affinity_prior(scale);
        AffinityRecord::new(key, posterior)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::{
        GpuAcceleration, HardwareBucket, HardwareProfile, OperatingSystem, SimdWidth, VramClass,
    };

    #[test]
    fn picks_highest_expected_value_under_seeded_sampling() {
        let hw = HardwareBucket::from_profile(HardwareProfile::new(
            VramClass::Vram8192,
            GpuAcceleration {
                cuda: true,
                metal: false,
                rocm: false,
                vulkan: false,
                opencl: false,
            },
            SimdWidth::Avx512,
            OperatingSystem::Linux,
        ));
        let task_key = AffinityKey::new(hw, "render");
        let weak = DispatchCandidate {
            peer_id: "peer-a".into(),
            hardware: hw,
            task_key: task_key.clone(),
            posterior: BetaPosterior::new(2.0, 8.0).unwrap(),
        };
        let strong = DispatchCandidate {
            peer_id: "peer-b".into(),
            hardware: hw,
            task_key,
            posterior: BetaPosterior::new(8.0, 2.0).unwrap(),
        };

        let decision = Dispatcher::with_seed(7).select(&[weak, strong]).unwrap();
        assert_eq!(decision.peer_id, "peer-b");
    }
}
