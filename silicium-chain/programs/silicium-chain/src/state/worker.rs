use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum WorkerStatus {
    Active,
    Banned,
}

#[account]
pub struct Worker {
    pub owner: Pubkey,

    pub stake_mint: Pubkey,
    pub stake_vault: Pubkey,

    pub stake_amount: u64,
    pub reputation: i64,

    pub total_submitted: u32,
    pub total_verified: u32,
    pub total_rejected: u32,

    pub status: WorkerStatus,
    pub bump: u8,
}

impl Worker {
    pub const SPACE: usize =
        8   // discr
        + 32 // owner
        + 32 // stake_mint
        + 32 // stake_vault
        + 8  // stake_amount
        + 8  // reputation
        + 4  // submitted
        + 4  // verified
        + 4  // rejected
        + 1  // status
        + 1; // bump
}
