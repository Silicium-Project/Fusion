use anchor_lang::prelude::*;

pub const ROLE_COMPUTE: u8 = 1;
pub const ROLE_VERIFY: u8 = 2;

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

    /// Final score of reputation
    pub reputation: i64,

    pub total_submitted: u64,
    pub total_verified: u64,
    pub total_rejected: u64,

    pub active_claims: u32,

    pub roles: u8,
    pub status: WorkerStatus,

    // V2: réputation bayésienne double mémoire pour les calculs.
    pub compute_alpha_long: u64,
    pub compute_beta_long: u64,
    pub compute_alpha_short: u64,
    pub compute_beta_short: u64,

    // V2: réputation bayésienne double mémoire pour la vérification.
    pub verify_alpha_long: u64,
    pub verify_beta_long: u64,
    pub verify_alpha_short: u64,
    pub verify_beta_short: u64,

    // V2: pénalités différenciées erreur / fraude.
    pub fraud_strikes: u16,
    pub error_strikes: u16,
    pub last_reputation_update: i64,

    // V2: scores utilisés par le scheduler off-chain.
    pub performance_score: u32,
    pub efficiency_score: u32,
    pub reliability_score: u32,

    pub bump: u8,
}

impl Worker {
    pub const SPACE: usize =
        8 +     // discriminator
        32 +    // owner
        32 +    // stake_mint
        32 +    // stake_vault
        8 +     // stake_amount
        8 +     // reputation
        8 +     // total_submitted
        8 +     // total_verified
        8 +     // total_rejected
        4 +     // active_claims
        1 +     // roles
        1 +     // status enum
        8 +     // compute_alpha_long
        8 +     // compute_beta_long
        8 +     // compute_alpha_short
        8 +     // compute_beta_short
        8 +     // verify_alpha_long
        8 +     // verify_beta_long
        8 +     // verify_alpha_short
        8 +     // verify_beta_short
        2 +     // fraud_strikes
        2 +     // error_strikes
        8 +     // last_reputation_update
        4 +     // performance_score
        4 +     // efficiency_score
        4 +     // reliability_score
        1;      // bump

    pub fn has_role(&self, role: u8) -> bool {
        self.roles & role != 0
    }
}
