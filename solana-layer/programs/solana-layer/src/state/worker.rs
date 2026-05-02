use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum WorkerStatus {
    Active,
    Suspended,
    Banned,
}

pub const ROLE_COMPUTE: u8 = 1 << 0;
pub const ROLE_VERIFY: u8  = 1 << 1;
pub const ROLE_ADMIN: u8   = 1 << 2;

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

    pub roles: u8,

    pub status: WorkerStatus,
    pub bump: u8,
}

impl Worker {
    pub fn has_role(&self, role: u8) -> bool {
        (self.roles & role) != 0
    }

    pub const SPACE: usize =
        8   // discr
        + 32 // owner
        + 32 // stake_mint
        + 32 // stake_vault
        + 8  // stake_amount
        + 8  // reputation (i64)
        + 4  // submitted
        + 4  // verified
        + 4  // rejected
        + 1  // roles (u8)  NEW
        + 1  // status (enum u8)
        + 1; // bump
}
