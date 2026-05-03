use anchor_lang::prelude::*;

pub const ROLE_COMPUTE: u8 = 1;
pub const ROLE_VERIFY: u8 = 2;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum WorkerStatus {
    Active,
    Suspended,
    Banned,
}

#[account]
pub struct Worker {
    pub owner: Pubkey,

    pub stake_mint: Pubkey,
    pub stake_vault: Pubkey,
    pub stake_amount: u64,

    pub reputation: i64,

    pub total_submitted: u64,
    pub total_verified: u64,
    pub total_rejected: u64,

    pub active_claims: u32,

    pub roles: u8,
    pub status: WorkerStatus,

    pub bump: u8,
}

impl Worker {
    pub const SPACE: usize =
        8 +     // discriminator
        32 +    // owner
        32 +    // stake_mint
        32 +    // stake_vault
        8 +     // stake_amount
        8 +     // reputation
        8 +     // total_submitted
        8 +     // total_verified
        8 +     // total_rejected
        4 +     // active_claims
        1 +     // roles
        1 +     // status enum
        1;      // bump

    pub fn has_role(&self, role: u8) -> bool {
        self.roles & role != 0
    }
}
