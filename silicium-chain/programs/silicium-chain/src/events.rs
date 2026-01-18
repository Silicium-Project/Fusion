use anchor_lang::prelude::*;

"""logs for the off-chain programm and the website
    for display the status of the workflow."""

#[event]
pub struct ConfigInitialized {
    pub admin: Pubkey,
    pub scheduler: Pubkey,
    pub mint: Pubkey,
    pub fee_bps: u16,
}

#[event]
pub struct WorkerRegistered {
    pub worker: Pubkey,
    pub owner: Pubkey,
    pub worker_id: u64,
}

#[event]
pub struct TaskSubmitted {
    pub task: Pubkey,
    pub authority: Pubkey,
    pub task_id: u64,
    pub nb_subtasks: u32,
    pub metadata_hash: [u8; 32],
}

#[event]
pub struct TaskFunded {
    pub task: Pubkey,
    pub amount: u64,
    pub total_budget: u64,
}

#[event]
pub struct WorkAssigned {
    pub task: Pubkey,
    pub assignment: Pubkey,
    pub assignment_id: u64,
    pub worker: Pubkey,
    pub subtask_index: u32,
    pub reward: u64,
    pub required_verifiers: u8,
}

#[event]
pub struct ResultSubmitted {
    pub assignment: Pubkey,
    pub worker: Pubkey,
    pub result_hash: [u8; 32],
}

#[event]
pub struct ResultVerified {
    pub assignment: Pubkey,
    pub verifier: Pubkey,
    pub approved: bool,
    pub approvals: u8,
    pub rejections: u8,
}

#[event]
pub struct AssignmentFinalized {
    pub assignment: Pubkey,
    pub approved: bool,
    pub worker_reward: u64,
    pub verifier_pool: u64,
    pub fee_amount: u64,
}

#[event]
pub struct RewardClaimed {
    pub claimant: Pubkey,
    pub amount: u64,
}

#[event]
pub struct WorkerSlashed {
    pub worker: Pubkey,
    pub penalty_reputation: i64,
    pub reason_code: u16,
}
