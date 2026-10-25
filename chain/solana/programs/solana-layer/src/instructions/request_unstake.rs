use anchor_lang::prelude::*;
use anchor_spl::token::Mint;

use crate::{
    constants::UNSTAKE_COOLDOWN_SECS,
    error::SiliciumError,
    events::NetworkUnstakeRequested,
    state::{network_staker::NetworkStaker, staking_pool::StakingPool},
};

#[derive(Accounts)]
pub struct RequestUnstake<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        mut,
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump = pool.bump,
        constraint = pool.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub pool: Account<'info, StakingPool>,

    #[account(
        mut,
        seeds = [
            b"network_staker",
            owner.key().as_ref(),
            mint.key().as_ref()
        ],
        bump = staker.bump,
        constraint = staker.owner == owner.key() @ SiliciumError::NotAuthorized,
        constraint = staker.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub staker: Account<'info, NetworkStaker>,
}

pub fn handler(ctx: Context<RequestUnstake>, amount: u64) -> Result<()> {
    require!(amount > 0, SiliciumError::InvalidAmount);

    let now = Clock::get()?.unix_timestamp;

    let pool = &mut ctx.accounts.pool;
    let staker = &mut ctx.accounts.staker;

    require!(
        staker.stake_amount >= amount,
        SiliciumError::InsufficientStakedAmount
    );

    let pending = staker.pending_reward_amount(pool)?;
    staker.pending_rewards = pending;

    staker.stake_amount = staker.stake_amount.saturating_sub(amount);
    pool.total_staked = pool.total_staked.saturating_sub(amount);

    staker.unstake_requested_amount = staker
        .unstake_requested_amount
        .checked_add(amount)
        .ok_or(SiliciumError::InvalidParams)?;

    staker.unstake_available_at = now.saturating_add(UNSTAKE_COOLDOWN_SECS);

    staker.refresh_reward_debt(pool)?;

    emit!(NetworkUnstakeRequested {
        pool: pool.key(),
        staker: staker.key(),
        owner: staker.owner,
        amount,
        remaining_stake: staker.stake_amount,
        available_at: staker.unstake_available_at,
    });

    Ok(())
}
