use anchor_lang::prelude::*;

"""A task submitted by a user + escrow budget + status."""

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum TaskStatus {
    Created,
    Funded,
    Assigned,
    Finalized,
    Cancelled,
}

#[account]
pub struct Task {
    pub authority: Pubkey,
    pub task_id: u64,
    pub status: TaskStatus,

    pub metadata_hash: [u8; 32],
    pub nb_subtasks: u32,

    pub total_budget: u64,
    pub remaining_budget: u64,

    pub created_at: i64,
    pub bump: u8,
}

impl Task {
    pub const SIZE: usize =
        8 + 32 + 8 + 1 + 32 + 4 + 8 + 8 + 8 + 1;
}
