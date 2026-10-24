use anchor_lang::prelude::*;

#[constant]
pub const SEED: &str = "anchor";

// Bootstrap access: newly registered workers/verifiers can participate in low-risk tasks without active stake.
// Per-fragment `required_stake` and high-risk actions such as split still enforce stake when needed.
pub const MIN_COMPUTE_STAKE: u64 = 0;
pub const MIN_VERIFIER_STAKE: u64 = 0;

pub const MIN_FRAGMENT_QUORUM: u16 = 2;

pub const SLASH_BPS: u64 = 1000; // 10%
pub const BPS_DENOM: u64 = 10_000;

pub const MIN_JOB_DEPOSIT: u64 = 1_000_000;

/// Maximum total fragment accounts, including internal split parents.
pub const MAX_FRAGMENTS_PER_JOB: u32 = 1_000;

pub const MIN_JOB_TTL_SECS: i64 = 60;
pub const MAX_JOB_TTL_SECS: i64 = 7 * 24 * 60 * 60;

pub const MAX_FRAGMENT_QUORUM: u16 = 10;
pub const VOTING_TTL_SECS: i64 = 300;

pub const MAX_ACTIVE_CLAIMS_PER_WORKER: u32 = 5;

pub const REWARD_SCALE: u128 = 1_000_000_000_000;

pub const MIN_NETWORK_STAKE: u64 = 1_000_000;

// 5 secondes pour les tests locaux.
// Pour une vraie beta/mainnet, mets plutôt : 3 * 24 * 60 * 60.
pub const UNSTAKE_COOLDOWN_SECS: i64 = 5;

// V2: sous-fragmentation contrôlée.
pub const DEFAULT_MAX_FRAGMENT_DEPTH: u8 = 4;
/// Maximum leaf payout slots relative to the initial pre-split count. This
/// matches the four binary delegation levels (2^4 leaves per initial root).
pub const DEFAULT_MAX_FRAGMENT_MULTIPLIER: u32 = 16;
/// Maximum children on one approved split.
pub const DEFAULT_MAX_CHILDREN_PER_FRAGMENT: u16 = 2;
// Binary child slots have a deterministic index inside each root fragment's
// reserved range, so independent splitters cannot allocate colliding PDAs.
pub const MAX_CHILDREN_PER_SPLIT: u16 = 2;
pub const SPLIT_MIN_REPUTATION: i64 = 5_000;
// Newly linked dev workers start with no stake. Bayesian reputation and the
// assigned-worker check remain the split gate; requiring stake here would
// make the 20 test workers unable to exercise recursive delegation.
pub const SPLIT_MIN_STAKE: u64 = 0;
pub const SPLIT_MIN_COMPLEXITY: u32 = 1_000;
pub const DEFAULT_ROOT_COMPLEXITY_SCORE: u32 = 1_000;
