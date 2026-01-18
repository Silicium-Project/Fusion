use anchor_lang::prelude::*;

"""register worker + reputation + stats."""

#[account]
pub struct Worker {
    pub owner: Pubkey,     // wallet controlling this worker
    pub worker_id: u64,
    pub reputation: i64,
    pub total_jobs: u64,
    pub success_jobs: u64,
    pub bump: u8,
}

impl Worker {
    pub const SIZE: usize = 8 + 32 + 8 + 8 + 8 + 8 + 1;
}
