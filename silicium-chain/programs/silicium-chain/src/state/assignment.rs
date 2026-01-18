use anchor_lang::prelude::*;

"""A subtask assigned to a worker + votes + calculated amounts + claim."""

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum AssignmentStatus {
    Assigned,
    Submitted,
    Finalized,
    Slashed,
}

#[account]
pub struct Assignment {
    pub task: Pubkey,
    pub worker: Pubkey,
    pub assignment_id: u64,
    pub subtask_index: u32,

    pub reward: u64,
    pub required_verifiers: u8,
    pub approvals: u8,
    pub rejections: u8,

    // Lightweight anti-double-vote (PFE-friendly). For production, use Vote PDAs.
    pub verifier_acc_hash: [u8; 32],

    pub result_hash: [u8; 32],
    pub result_deadline: i64,

    pub status: AssignmentStatus,

    pub worker_reward: u64,
    pub verifier_pool: u64,
    pub fee_amount: u64,

    pub worker_claimed: bool,

    pub bump: u8,
}

impl Assignment {
    pub const SIZE: usize =
        8
        + 32 + 32 + 8 + 4
        + 8 + 1 + 1 + 1
        + 32
        + 32 + 8
        + 1
        + 8 + 8 + 8
        + 1
        + 1;
}
