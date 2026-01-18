use anchor_lang::prelude::*;

"""Centralizing PDA seeds and constants used everywhere"""

#[constant]
pub const SEED_CONFIG: &[u8] = b"config";
pub const SEED_WORKER: &[u8] = b"worker";
pub const SEED_TASK: &[u8] = b"task";
pub const SEED_ASSIGNMENT: &[u8] = b"assign";
pub const SEED_VAULT_AUTH: &[u8] = b"vault_auth";
