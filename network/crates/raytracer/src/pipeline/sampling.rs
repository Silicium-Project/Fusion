//! Probabilistic verification of milestones: the lower a worker's reputation,
//! the more milestones are re-checked; the sample is chosen from a seed drawn
//! after the commitment, so the worker cannot predict it.

use super::{ppm, py_round, sha256_hex};
use serde::{Deserialize, Serialize};

/// Minimal part of a milestone manifest needed to verify it.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct SampledManifest {
    #[serde(default)]
    pub fragment_y_start: i64,
    #[serde(default)]
    pub milestone_count: usize,
    #[serde(default)]
    pub milestones: Vec<SampledMilestone>,
}

/// Minimal part of a milestone needed to verify it.
#[derive(Debug, Clone, Deserialize)]
pub struct SampledMilestone {
    pub index: usize,
    pub y_start: i64,
    pub y_end: i64,
    pub pixel_sha256: String,
}

/// A milestone whose recomputed hash differs.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FailedMilestone {
    pub index: usize,
    pub expected: String,
    pub actual: String,
}

/// Outcome of a probabilistic verification.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VerificationResult {
    pub verified: bool,
    pub escalated_to_full: bool,
    pub sample_rate: f64,
    pub sampled_count: usize,
    pub total_milestones: usize,
    pub failed_milestones: Vec<FailedMilestone>,
    pub reason: String,
}

/// Share of milestones to check: 100 % at reputation 0, 20 % from reputation 100.
pub fn sampling_rate(reputation: f64) -> f64 {
    let (min_rate, max_rate) = (0.2, 1.0);
    let reputation = reputation.max(0.0);
    if reputation >= 100.0 {
        return min_rate;
    }
    let rate = max_rate - (reputation / 100.0) * (max_rate - min_rate);
    py_round(rate.min(max_rate).max(min_rate), 4)
}

/// Milestone indexes to check, chosen by `sha256("{seed}:{index}")`.
pub fn select(indexes: &[usize], seed: &str, sample_rate: f64) -> Vec<usize> {
    if indexes.is_empty() {
        return Vec::new();
    }
    let sample_rate = sample_rate.clamp(0.0, 1.0);
    let target = ((indexes.len() as f64 * sample_rate).ceil() as usize).max(1);
    let mut scored: Vec<(String, usize)> = indexes
        .iter()
        .map(|index| (sha256_hex(format!("{seed}:{index}").as_bytes()), *index))
        .collect();
    scored.sort_by(|left, right| left.0.cmp(&right.0));
    scored
        .into_iter()
        .take(target)
        .map(|(_, index)| index)
        .collect()
}

/// Probability that sampling `sampled` of `total` milestones catches at least
/// one of `tampered` altered milestones.
pub fn detection_probability(total: usize, tampered: usize, sampled: usize) -> f64 {
    if total == 0 || sampled == 0 || tampered == 0 {
        return 0.0;
    }
    if tampered >= total || sampled >= total {
        return 1.0;
    }
    let mut miss = 1.0;
    for i in 0..sampled {
        miss *= (total - tampered - i) as f64 / (total - i) as f64;
    }
    py_round(1.0 - miss, 4)
}

/// Checks a sample of the milestones of `tile_ppm` against `manifest`.
pub fn verify(
    tile_ppm: &[u8],
    manifest: &SampledManifest,
    seed: &str,
    reputation: f64,
) -> Result<VerificationResult, String> {
    let image = ppm::parse(tile_ppm, "<bytes>")?;
    let stride = image.width as i64 * 3;
    let sample_rate = sampling_rate(reputation);
    let indexes: Vec<usize> = manifest.milestones.iter().map(|item| item.index).collect();
    let chosen = select(&indexes, seed, sample_rate);
    let mut failed = Vec::new();
    for index in &chosen {
        let Some(milestone) = manifest.milestones.iter().find(|item| item.index == *index) else {
            continue;
        };
        let start = (milestone.y_start - manifest.fragment_y_start) * stride;
        let end = (milestone.y_end - manifest.fragment_y_start) * stride;
        let len = image.pixels.len() as i64;
        let (start, end) = (start.clamp(0, len) as usize, end.clamp(0, len) as usize);
        let actual = sha256_hex(image.pixels.get(start..end.max(start)).unwrap_or(&[]));
        if actual != milestone.pixel_sha256 {
            failed.push(FailedMilestone {
                index: milestone.index,
                expected: milestone.pixel_sha256.clone(),
                actual,
            });
        }
    }
    let verified = failed.is_empty();
    Ok(VerificationResult {
        verified,
        escalated_to_full: !verified,
        sample_rate,
        sampled_count: chosen.len(),
        total_milestones: manifest.milestone_count,
        reason: if verified {
            String::new()
        } else {
            format!(
                "probabilistic_milestone_verification_failed:{}_mismatches",
                failed.len()
            )
        },
        failed_milestones: failed,
    })
}
