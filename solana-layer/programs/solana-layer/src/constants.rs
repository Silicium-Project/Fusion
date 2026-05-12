use anchor_lang::prelude::*;

#[constant]
pub const SEED: &str = "anchor";

pub const MIN_COMPUTE_STAKE: u64 = 1;
pub const MIN_VERIFIER_STAKE: u64 = 1;

pub const MIN_FRAGMENT_QUORUM: u16 = 2;

pub const SLASH_BPS: u64 = 1000; // 10%
pub const BPS_DENOM: u64 = 10_000;

pub const MIN_JOB_DEPOSIT: u64 = 1_000_000;

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
pub const DEFAULT_MAX_FRAGMENT_MULTIPLIER: u32 = 8;
pub const DEFAULT_MAX_CHILDREN_PER_FRAGMENT: u16 = 8;
pub const MAX_CHILDREN_PER_SPLIT: u16 = 8;
pub const SPLIT_MIN_REPUTATION: i64 = 8_500;
pub const SPLIT_MIN_STAKE: u64 = 1_000;
pub const SPLIT_MIN_COMPLEXITY: u32 = 6_000;
pub const DEFAULT_ROOT_COMPLEXITY_SCORE: u32 = 1_000;
