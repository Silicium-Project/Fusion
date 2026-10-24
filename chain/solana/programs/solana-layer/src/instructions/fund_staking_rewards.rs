use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    constants::REWARD_SCALE,
    error::SiliciumError,
    events::StakingRewardsFunded,
    state::staking_pool::StakingPool,
};

#[derive(Accounts)]
pub struct FundStakingRewards<'info> {
    #[account(mut)]
    pub funder: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        mut,
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump = pool.bump,
        constraint = pool.mint == mint.key() @ SiliciumError::InvalidParams,
        constraint = pool.reward_vault == reward_vault.key() @ SiliciumError::InvalidParams
    )]
    pub pool: Account<'info, StakingPool>,

    #[account(
        mut,
        constraint = funder_token.owner == funder.key() @ SiliciumError::NotAuthorized,
        constraint = funder_token.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub funder_token: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = reward_vault.key() == pool.reward_vault @ SiliciumError::InvalidParams,
        constraint = reward_vault.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub reward_vault: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<FundStakingRewards>, amount: u64) -> Result<()> {
    require!(amount > 0, SiliciumError::InvalidAmount);
    require!(ctx.accounts.pool.total_staked > 0, SiliciumError::NoStakers);

    let cpi_ctx = CpiContext::new(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.funder_token.to_account_info(),
            to: ctx.accounts.reward_vault.to_account_info(),
            authority: ctx.accounts.funder.to_account_info(),
        },
    );

    token::transfer(cpi_ctx, amount)?;

    let pool = &mut ctx.accounts.pool;

    let reward_per_share_delta = (amount as u128)
        .checked_mul(REWARD_SCALE)
        .ok_or(SiliciumError::InvalidParams)?
        .checked_div(pool.total_staked as u128)
        .ok_or(SiliciumError::InvalidParams)?;

    pool.acc_reward_per_share = pool
        .acc_reward_per_share
        .checked_add(reward_per_share_delta)
        .ok_or(SiliciumError::InvalidParams)?;

    emit!(StakingRewardsFunded {
        pool: pool.key(),
        funder: ctx.accounts.funder.key(),
        amount,
        total_staked: pool.total_staked,
        acc_reward_per_share: pool.acc_reward_per_share,
    });

    Ok(())
}
