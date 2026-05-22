use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, PartialEq, Eq)]
pub enum JobStatus {
    Open,
    Finalized,
    Cancelled,
}

#[account]
pub struct Job {
    pub job_id: u64,
    pub client: Pubkey,
    pub mint: Pubkey,
    pub escrow: Pubkey,

    /// En V2, ceci représente le nombre de fragments leaf attendus.
    pub expected_fragments: u32,
    pub verified_fragments: u32,

    pub reward_per_fragment: u64,
    pub verifier_reward_per_vote: u64,
    pub verifier_reward_budget: u64,

    pub deposited_amount: u64,
    pub paid_amount: u64,

    pub claimable_verifier_rewards_total: u64,
    pub claimed_verifier_rewards_total: u64,

    pub created_at_unix: i64,
    pub deadline_unix: i64,
    pub verified_at_unix: i64,

    pub fragment_quorum: u16,

    // V2: garde-fous de sous-fragmentation.
    pub max_fragments: u32,
    pub total_fragments_created: u32,
    pub max_fragment_depth: u8,
    pub split_authority: Pubkey,

    pub status: JobStatus,

    pub bump: u8,
    pub escrow_auth_bump: u8,
}

impl Job {
    pub const SPACE: usize = 8  // discriminator
        + 8                     // job_id
        + 32                    // client
        + 32                    // mint
        + 32                    // escrow
        + 4                     // expected_fragments
        + 4                     // verified_fragments
        + 8                     // reward_per_fragment
        + 8                     // verifier_reward_per_vote
        + 8                     // verifier_reward_budget
        + 8                     // deposited_amount
        + 8                     // paid_amount
        + 8                     // claimable_verifier_rewards_total
        + 8                     // claimed_verifier_rewards_total
        + 8                     // created_at_unix
        + 8                     // deadline_unix
        + 8                     // verified_at_unix
        + 2                     // fragment_quorum
        + 4                     // max_fragments
        + 4                     // total_fragments_created
        + 1                     // max_fragment_depth
        + 32                    // split_authority
        + 1                     // status
        + 1                     // bump
        + 1;                    // escrow_auth_bump
}
