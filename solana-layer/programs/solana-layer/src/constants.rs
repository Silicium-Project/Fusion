use anchor_lang::prelude::*;

#[constant]
pub const SEED: &str = "anchor";

pub const MIN_COMPUTE_STAKE: u64 = 1;
pub const MIN_VERIFIER_STAKE: u64 = 1;

pub const MIN_FRAGMENT_QUORUM: u16 = 2;

pub const SLASH_BPS: u64 = 1000; // 10%
pub const BPS_DENOM: u64 = 10_000;