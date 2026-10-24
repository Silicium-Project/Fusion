use anchor_lang::prelude::*;

/// On-chain destination for a worker's compute and verifier rewards.
///
/// The account wallet is chosen by an account that controls the worker. A
/// worker signature is checked from the Ed25519 precompile instruction in the
/// same transaction, so neither the website nor the backend can redirect a
/// worker's rewards on its own.
#[account]
pub struct WorkerPayout {
    pub worker: Pubkey,
    pub payout_wallet: Pubkey,
    pub bump: u8,
}

impl WorkerPayout {
    pub const SPACE: usize = 8 + 32 + 32 + 1;
}
