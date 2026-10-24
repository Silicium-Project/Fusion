use anchor_lang::prelude::*;

#[account]
pub struct StakingPool {
    pub mint: Pubkey,

    pub authority: Pubkey,
    pub stake_vault: Pubkey,
    pub reward_vault: Pubkey,

    pub total_staked: u64,
    pub acc_reward_per_share: u128,

    pub bump: u8,
    pub authority_bump: u8,
}

impl StakingPool {
    pub const SPACE: usize =
        8 +     // discriminator
        32 +    // mint
        32 +    // authority
        32 +    // stake_vault
        32 +    // reward_vault
        8 +     // total_staked
        16 +    // acc_reward_per_share
        1 +     // bump
        1;      // authority_bump
}
