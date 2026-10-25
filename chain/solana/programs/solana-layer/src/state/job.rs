use anchor_lang::prelude::*;

use crate::constants::{DEFAULT_MAX_FRAGMENT_MULTIPLIER, MAX_FRAGMENTS_PER_JOB};

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
    /// Maximum number of fragment accounts, including internal split nodes.
    pub max_fragments: u32,
    pub total_fragments_created: u32,
    pub max_fragment_depth: u8,
    pub split_authority: Pubkey,

    pub status: JobStatus,

    pub bump: u8,
    pub escrow_auth_bump: u8,
}

impl Job {
    /// Reconstructs the original root count from the leaf and node totals.
    /// For binary splits, each split adds one expected leaf and two created
    /// fragment accounts, so `2 * leaves - nodes` stays equal to the roots.
    pub fn initial_fragments(&self) -> u32 {
        self.expected_fragments
            .checked_mul(2)
            .and_then(|value| value.checked_sub(self.total_fragments_created))
            .unwrap_or(0)
    }

    /// Maximum payable leaves given the job's initial roots and reserved
    /// binary-tree account range. A binary split consumes two child accounts
    /// but adds only one payable leaf.
    pub fn max_leaf_fragments(&self) -> u32 {
        let initial_fragments = self.initial_fragments();
        if initial_fragments == 0 {
            return 0;
        }
        let child_slots_per_root =
            self.max_fragments.saturating_sub(initial_fragments) / initial_fragments;
        let leaves_per_root = 1 + child_slots_per_root / 2;
        initial_fragments
            .saturating_mul(leaves_per_root)
            .min(initial_fragments.saturating_mul(DEFAULT_MAX_FRAGMENT_MULTIPLIER))
            .min(MAX_FRAGMENTS_PER_JOB)
    }

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
        + 1; // escrow_auth_bump
}
