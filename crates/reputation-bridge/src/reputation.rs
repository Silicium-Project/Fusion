//! Per-peer reputation with short- and long-term memory (two Beta posteriors with different half-lives).

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::Instant;

/// Bayesian dual-memory reputation model with time decay.
/// Ported from BackEnd/internal/reputation/bayesian.go
#[derive(Debug)]
pub struct DualMemoryBayes {
    short_half_life_s: f64,
    long_half_life_s: f64,
    short_alpha: f64,
    short_beta: f64,
    long_alpha: f64,
    long_beta: f64,
    last_update: Instant,
}

impl DualMemoryBayes {
    pub fn new(short_half_life_s: f64, long_half_life_s: f64) -> Self {
        Self {
            short_half_life_s,
            long_half_life_s,
            short_alpha: 1.0,
            short_beta: 1.0,
            long_alpha: 1.0,
            long_beta: 1.0,
            last_update: Instant::now(),
        }
    }

    pub fn observe(&mut self, success: bool, weight: f64) {
        let dt = self.last_update.elapsed().as_secs_f64();

        if dt > 0.0 {
            let decay_short = (-dt * std::f64::consts::LN_2 / self.short_half_life_s).exp();
            let decay_long = (-dt * std::f64::consts::LN_2 / self.long_half_life_s).exp();

            self.short_alpha = 1.0 + (self.short_alpha - 1.0) * decay_short;
            self.short_beta = 1.0 + (self.short_beta - 1.0) * decay_short;
            self.long_alpha = 1.0 + (self.long_alpha - 1.0) * decay_long;
            self.long_beta = 1.0 + (self.long_beta - 1.0) * decay_long;
        }
        self.last_update = Instant::now();

        if success {
            self.short_alpha += weight;
            self.long_alpha += weight;
        } else {
            self.short_beta += weight;
            self.long_beta += weight;
        }
    }

    /// Returns a blended score [0.0, 1.0]: 70% long-term, 30% short-term.
    pub fn score(&self) -> f64 {
        let short_score = self.short_alpha / (self.short_alpha + self.short_beta);
        let long_score = self.long_alpha / (self.long_alpha + self.long_beta);
        (long_score * 0.7) + (short_score * 0.3)
    }
}

#[derive(Debug, Default)]
pub struct ReputationStore {
    scores: HashMap<String, DualMemoryBayes>,
}

impl ReputationStore {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn observe_peer(&mut self, peer_id: &str, success: bool, weight: f64) {
        let entry = self.scores.entry(peer_id.to_string()).or_insert_with(|| {
            // Default: 24h short-term, 30d long-term
            DualMemoryBayes::new(86_400.0, 2_592_000.0)
        });
        entry.observe(success, weight);
    }

    pub fn get_score(&self, peer_id: &str) -> f64 {
        self.scores
            .get(peer_id)
            .map(|dmb| dmb.score())
            .unwrap_or(0.5) // Default: unknown
    }
}

pub type SharedReputationStore = Arc<RwLock<ReputationStore>>;

pub fn new_shared_store() -> SharedReputationStore {
    Arc::new(RwLock::new(ReputationStore::new()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_unknown_score() {
        let store = ReputationStore::new();
        assert_eq!(store.get_score("unknown_peer"), 0.5);
    }

    #[test]
    fn test_positive_observations_increase_score() {
        let mut store = ReputationStore::new();
        for _ in 0..10 {
            store.observe_peer("peer1", true, 1.0);
        }
        assert!(store.get_score("peer1") > 0.5);
    }

    #[test]
    fn test_negative_observations_decrease_score() {
        let mut store = ReputationStore::new();
        for _ in 0..10 {
            store.observe_peer("peer2", false, 1.0);
        }
        assert!(store.get_score("peer2") < 0.5);
    }
}
