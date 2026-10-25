use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    constants::MIN_NETWORK_STAKE,
    error::SiliciumError,
    events::NetworkStakeDeposited,
    state::{network_staker::NetworkStaker, staking_pool::StakingPool},
};

#[derive(Accounts)]
pub struct StakeNetwork<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        mut,
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump = pool.bump,
        constraint = pool.mint == mint.key() @ SiliciumError::InvalidParams,
        constraint = pool.stake_vault == stake_vault.key() @ SiliciumError::InvalidParams
    )]
    pub pool: Account<'info, StakingPool>,

    #[account(
        init_if_needed,
        payer = owner,
        space = NetworkStaker::SPACE,
        seeds = [
            b"network_staker",
            owner.key().as_ref(),
            mint.key().as_ref()
        ],
        bump
    )]
    pub staker: Account<'info, NetworkStaker>,

    #[account(
        mut,
        constraint = owner_token.owner == owner.key() @ SiliciumError::NotAuthorized,
        constraint = owner_token.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub owner_token: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = stake_vault.key() == pool.stake_vault @ SiliciumError::InvalidParams,
        constraint = stake_vault.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub stake_vault: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<StakeNetwork>, amount: u64) -> Result<()> {
    require!(amount >= MIN_NETWORK_STAKE, SiliciumError::InvalidAmount);

    let pool = &mut ctx.accounts.pool;
    let staker = &mut ctx.accounts.staker;

    if staker.owner == Pubkey::default() {
        staker.owner = ctx.accounts.owner.key();
        staker.mint = ctx.accounts.mint.key();
        staker.stake_amount = 0;
        staker.reward_debt = 0;
        staker.pending_rewards = 0;
        staker.unstake_requested_amount = 0;
        staker.unstake_available_at = 0;
        staker.bump = ctx.bumps.staker;
    } else {
        require!(
            staker.owner == ctx.accounts.owner.key(),
            SiliciumError::NotAuthorized
        );

        require!(
            staker.mint == ctx.accounts.mint.key(),
            SiliciumError::InvalidParams
        );
    }

    let pending = staker.pending_reward_amount(pool)?;
    staker.pending_rewards = pending;

    let cpi_ctx = CpiContext::new(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.owner_token.to_account_info(),
            to: ctx.accounts.stake_vault.to_account_info(),
            authority: ctx.accounts.owner.to_account_info(),
        },
    );

    token::transfer(cpi_ctx, amount)?;

    staker.stake_amount = staker
        .stake_amount
        .checked_add(amount)
        .ok_or(SiliciumError::InvalidParams)?;

    pool.total_staked = pool
        .total_staked
        .checked_add(amount)
        .ok_or(SiliciumError::InvalidParams)?;

    staker.refresh_reward_debt(pool)?;

    emit!(NetworkStakeDeposited {
        pool: pool.key(),
        staker: staker.key(),
        owner: staker.owner,
        amount,
        total_staked: pool.total_staked,
        user_stake_amount: staker.stake_amount,
    });

    Ok(())
}
