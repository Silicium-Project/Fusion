//! Which passages a verifier recomputes.
//!
//! Recomputing every vector would cost the verifier as much as the worker.
//! The verifier instead recomputes a few passages drawn from a seed the
//! worker could not know when it computed (the publisher's acceptance of
//! the verifier, see `p2p_node::verifier`). A worker that faked a fraction
//! `f` of its vectors is caught with probability `1 - (1 - f)^k` for `k`
//! passages drawn: certainly when it faked everything, about 2 times out of
//! 3 for a quarter of its vectors with `k = 4`, and repeated jobs plus the
//! reputation do the rest.
//!
//! The draw is deterministic (SHA-256 of the seed and a counter), so that
//! anyone can redo it and check which passages a verdict covered.

use sha2::{Digest, Sha256};

/// Passages to recompute for a fragment of `count` passages: 2 % of them,
/// at least 3 (or all when fewer) and at most 8.
pub fn sample_size(count: usize) -> usize {
    count.div_ceil(50).clamp(3, 8).min(count)
}

/// `k` distinct indices below `count`, drawn from `seed`, in draw order.
pub fn sample_indices(seed: &str, count: usize, k: usize) -> Vec<usize> {
    let k = k.min(count);
    let mut picked = Vec::with_capacity(k);
    let mut counter: u64 = 0;
    while picked.len() < k {
        let mut hasher = Sha256::new();
        hasher.update(seed.as_bytes());
        hasher.update(counter.to_le_bytes());
        let digest = hasher.finalize();
        let value = u64::from_le_bytes(digest[..8].try_into().expect("8 bytes"));
        let index = (value % count as u64) as usize;
        if !picked.contains(&index) {
            picked.push(index);
        }
        counter += 1;
    }
    picked
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_sample_grows_slowly_with_the_fragment() {
        assert_eq!(sample_size(1), 1);
        assert_eq!(sample_size(2), 2);
        assert_eq!(sample_size(100), 3);
        assert_eq!(sample_size(200), 4);
        assert_eq!(sample_size(10_000), 8);
    }

    #[test]
    fn draws_are_deterministic_distinct_and_seed_dependent() {
        let first = sample_indices("acceptance-a", 200, 4);
        assert_eq!(first, sample_indices("acceptance-a", 200, 4));
        assert_ne!(first, sample_indices("acceptance-b", 200, 4));
        let mut unique = first.clone();
        unique.sort_unstable();
        unique.dedup();
        assert_eq!(unique.len(), 4);
        assert!(first.iter().all(|index| *index < 200));
        assert_eq!(sample_indices("s", 3, 10).len(), 3, "never more than count");
        assert!(sample_indices("s", 0, 4).is_empty());
    }
}
