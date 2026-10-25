use anchor_lang::prelude::*;

pub const ROLE_COMPUTE: u8 = 1;
pub const ROLE_VERIFY: u8 = 2;

/// Optional role preference used by the off-chain scheduler.
/// It does not block the worker on-chain: every registered participant can still
/// compute and verify if they keep enough stake and reputation.
pub const ROLE_AUTO: u8 = 0;
pub const ROLE_COMPUTE_PREFERRED: u8 = 1;
pub const ROLE_VERIFY_PREFERRED: u8 = 2;

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

    /// Score used when this participant acts as a compute worker.
    pub compute_reputation: i64,

    /// Score used when this participant acts as a verifier.
    pub verify_reputation: i64,

    /// Derived global score used by dashboards and scheduler heuristics.
    pub global_reputation: i64,

    pub total_submitted: u64,
    pub total_verified: u64,
    pub total_rejected: u64,

    /// V2.5: role-specific counters for scheduler analytics.
    pub compute_jobs_done: u64,
    pub verify_jobs_done: u64,
    pub compute_failures: u64,
    pub verify_failures: u64,

    pub active_claims: u32,

    pub roles: u8,
    pub preferred_role: u8,
    pub status: WorkerStatus,

    // V2/V2.5: Bayesian double memory for compute reliability.
    pub compute_alpha_long: u64,
    pub compute_beta_long: u64,
    pub compute_alpha_short: u64,
    pub compute_beta_short: u64,

    // V2/V2.5: Bayesian double memory for verification reliability.
    pub verify_alpha_long: u64,
    pub verify_beta_long: u64,
    pub verify_alpha_short: u64,
    pub verify_beta_short: u64,

    // V2.5: separate fraud counters for compute and verify behavior.
    pub compute_fraud_strikes: u16,
    pub verify_fraud_strikes: u16,

    // Backward-compatible aggregate counters.
    pub fraud_strikes: u16,
    pub error_strikes: u16,
    pub last_reputation_update: i64,

    // V2: scores used by the off-chain scheduler.
    pub performance_score: u32,
    pub efficiency_score: u32,
    pub reliability_score: u32,

    pub bump: u8,
}

impl Worker {
    pub const SPACE: usize = 8 +     // discriminator
        32 +    // owner
        32 +    // stake_mint
        32 +    // stake_vault
        8 +     // stake_amount
        8 +     // compute_reputation
        8 +     // verify_reputation
        8 +     // global_reputation
        8 +     // total_submitted
        8 +     // total_verified
        8 +     // total_rejected
        8 +     // compute_jobs_done
        8 +     // verify_jobs_done
        8 +     // compute_failures
        8 +     // verify_failures
        4 +     // active_claims
        1 +     // roles
        1 +     // preferred_role
        1 +     // status enum
        8 +     // compute_alpha_long
        8 +     // compute_beta_long
        8 +     // compute_alpha_short
        8 +     // compute_beta_short
        8 +     // verify_alpha_long
        8 +     // verify_beta_long
        8 +     // verify_alpha_short
        8 +     // verify_beta_short
        2 +     // compute_fraud_strikes
        2 +     // verify_fraud_strikes
        2 +     // fraud_strikes
        2 +     // error_strikes
        8 +     // last_reputation_update
        4 +     // performance_score
        4 +     // efficiency_score
        4 +     // reliability_score
        1; // bump

    pub fn has_role(&self, role: u8) -> bool {
        self.roles & role != 0
    }
}
