use anchor_lang::prelude::*;

use crate::{constants::REWARD_SCALE, error::SiliciumError, state::staking_pool::StakingPool};

#[account]
pub struct NetworkStaker {
    pub owner: Pubkey,
    pub mint: Pubkey,

    pub stake_amount: u64,
    pub reward_debt: u128,
    pub pending_rewards: u64,

    pub unstake_requested_amount: u64,
    pub unstake_available_at: i64,

    pub bump: u8,
}

impl NetworkStaker {
    pub const SPACE: usize = 8 +     // discriminator
        32 +    // owner
        32 +    // mint
        8 +     // stake_amount
        16 +    // reward_debt
        8 +     // pending_rewards
        8 +     // unstake_requested_amount
        8 +     // unstake_available_at
        1; // bump

    pub fn pending_reward_amount(&self, pool: &StakingPool) -> Result<u64> {
        let accumulated = (self.stake_amount as u128)
            .checked_mul(pool.acc_reward_per_share)
            .ok_or(SiliciumError::InvalidParams)?
            .checked_div(REWARD_SCALE)
            .ok_or(SiliciumError::InvalidParams)?;

        let newly_pending = accumulated.saturating_sub(self.reward_debt);

        let total_pending = (self.pending_rewards as u128)
            .checked_add(newly_pending)
            .ok_or(SiliciumError::InvalidParams)?;

        require!(
            total_pending <= u64::MAX as u128,
            SiliciumError::InvalidParams
        );

        Ok(total_pending as u64)
    }

    pub fn refresh_reward_debt(&mut self, pool: &StakingPool) -> Result<()> {
        self.reward_debt = (self.stake_amount as u128)
            .checked_mul(pool.acc_reward_per_share)
            .ok_or(SiliciumError::InvalidParams)?
            .checked_div(REWARD_SCALE)
            .ok_or(SiliciumError::InvalidParams)?;

        Ok(())
    }
}
