use anchor_lang::prelude::*;

#[event]
pub struct JobCreated {
    pub job: Pubkey,
    pub client: Pubkey,
    pub mint: Pubkey,
    pub escrow: Pubkey,
    pub job_id: u64,
    pub expected_fragments: u32,
    pub reward_per_fragment: u64,
    pub deposited_amount: u64,
    pub deadline_unix: i64,
    pub fragment_quorum: u16,
}

#[event]
pub struct FragmentSubmitted {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub worker_token_account: Pubkey,
    pub round: u16,
    pub result_hash: [u8; 32],
    pub proof_ref: [u8; 32],
}

#[event]
pub struct FragmentVerified {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub verifier: Pubkey,
    pub reward: u64,
    pub yes_votes: u16,
    pub round: u16,
    pub verified_fragments: u32,
    pub expected_fragments: u32,
}

#[event]
pub struct FragmentRejected {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub verifier: Pubkey,
    pub no_votes: u16,
    pub round: u16,
}

#[event]
pub struct JobFinalized {
    pub job: Pubkey,
    pub client: Pubkey,
    pub result: Pubkey,
    pub final_hash: [u8; 32],
    pub refunded_amount: u64,
    pub verified_fragments: u32,
    pub expected_fragments: u32,
}

#[event]
pub struct JobCancelled {
    pub job: Pubkey,
    pub client: Pubkey,
    pub refunded_amount: u64,
}

#[event]
pub struct VoteSlashed {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub vote: Pubkey,
    pub verifier: Pubkey,
    pub slash_amount: u64,
    pub round: u16,
    pub fragment_status: u8,
    pub treasury: Pubkey,
}
