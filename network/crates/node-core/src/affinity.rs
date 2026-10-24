//! Affinity between a hardware bucket and a task, used to rank candidate nodes.

use crate::{beta::BetaPosterior, hardware::HardwareBucket};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AffinityKey {
    pub hardware: HardwareBucket,
    pub task: String,
}

impl AffinityKey {
    pub fn new(hardware: HardwareBucket, task: impl Into<String>) -> Self {
        Self {
            hardware,
            task: task.into(),
        }
    }

    pub fn to_record_key(&self) -> String {
        format!(
            "silicium/affinity/v1/{:08x}/{}",
            self.hardware.bits(),
            self.task
        )
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AffinityRecord {
    pub key: AffinityKey,
    pub posterior: BetaPosterior,
    pub observed_successes: u64,
    pub observed_failures: u64,
}

impl AffinityRecord {
    pub fn new(key: AffinityKey, posterior: BetaPosterior) -> Self {
        Self {
            key,
            posterior,
            observed_successes: 0,
            observed_failures: 0,
        }
    }

    pub fn observe(&mut self, success: bool, weight: f64) {
        self.posterior.observe(success, weight);
        if success {
            self.observed_successes += 1;
        } else {
            self.observed_failures += 1;
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TaskScale {
    pub hardware_weight: u32,
    pub task_weight: u32,
}

impl TaskScale {
    pub fn ratio(self) -> f64 {
        if self.task_weight == 0 {
            return 1.0;
        }
        (self.hardware_weight as f64 / self.task_weight as f64).clamp(0.0, 1.0)
    }
}

pub fn sparse_affinity_prior(scale: TaskScale) -> BetaPosterior {
    BetaPosterior::with_scale_hint(scale.ratio())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hardware::{
        GpuAcceleration, HardwareBucket, HardwareProfile, OperatingSystem, SimdWidth, VramClass,
    };

    #[test]
    fn record_key_is_versioned() {
        let key = AffinityKey::new(
            HardwareBucket::from_profile(HardwareProfile::new(
                VramClass::Vram4096,
                GpuAcceleration::default(),
                SimdWidth::Avx2,
                OperatingSystem::Linux,
            )),
            "render.pass.composite",
        );
        assert!(key.to_record_key().starts_with("silicium/affinity/v1/"));
    }

    #[test]
    fn sparse_prior_stays_valid() {
        let prior = sparse_affinity_prior(TaskScale {
            hardware_weight: 3,
            task_weight: 9,
        });
        assert!(prior.alpha() > 0.0);
        assert!(prior.beta() > 0.0);
    }
}
