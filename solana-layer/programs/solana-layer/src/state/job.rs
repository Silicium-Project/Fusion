use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum JobStatus {
    Open,
    Cancelled,
    Finalized,
}

#[account]
pub struct Job {
    pub job_id: u64,
    pub client: Pubkey,

    pub mint: Pubkey,
    pub escrow: Pubkey,

    pub expected_fragments: u32,
    pub verified_fragments: u32,

    pub reward_per_fragment: u64,
    pub deposited_amount: u64,
    pub paid_amount: u64,

    pub deadline_unix: i64,
    pub status: JobStatus,

    pub fragment_quorum: u16,

    pub verified_at_unix: i64,

    pub bump: u8,
    pub escrow_auth_bump: u8,
}

impl Job {
    pub const SPACE: usize =
        8   // discr
        + 8  // job_id
        + 32 // client
        + 32 // mint
        + 32 // escrow
        + 4  // expected_fragments
        + 4  // verified_fragments
        + 8  // reward_per_fragment
        + 8  // deposited_amount
        + 8  // paid_amount
        + 8  // deadline_unix
        + 1  // status
        + 2  // fragment_quorum
        + 8  // verified_at_unix
        + 1  // bump
        + 1; // escrow_auth_bump
}
