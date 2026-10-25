use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::StakingRewardClaimed,
    state::{network_staker::NetworkStaker, staking_pool::StakingPool},
};

#[derive(Accounts)]
pub struct ClaimStakingReward<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        mut,
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump = pool.bump,
        constraint = pool.mint == mint.key() @ SiliciumError::InvalidParams,
        constraint = pool.reward_vault == reward_vault.key() @ SiliciumError::InvalidParams,
        constraint = pool.authority == pool_auth.key() @ SiliciumError::NotAuthorized
    )]
    pub pool: Account<'info, StakingPool>,

    /// CHECK: PDA authority for reward vault
    #[account(
        seeds = [b"staking_pool_auth", mint.key().as_ref()],
        bump = pool.authority_bump
    )]
    pub pool_auth: UncheckedAccount<'info>,

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

    #[account(
        mut,
        constraint = reward_vault.key() == pool.reward_vault @ SiliciumError::InvalidParams,
        constraint = reward_vault.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub reward_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = owner_reward_token.owner == owner.key() @ SiliciumError::NotAuthorized,
        constraint = owner_reward_token.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub owner_reward_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ClaimStakingReward>) -> Result<()> {
    let pool = &ctx.accounts.pool;
    let staker = &mut ctx.accounts.staker;

    let amount = staker.pending_reward_amount(pool)?;

    require!(amount > 0, SiliciumError::NoStakingRewards);

    require!(
        ctx.accounts.reward_vault.amount >= amount,
        SiliciumError::InsufficientEscrow
    );

    let mint_key = ctx.accounts.mint.key();
    let bump = pool.authority_bump;

    let seeds: &[&[u8]] = &[b"staking_pool_auth", mint_key.as_ref(), &[bump]];
    let signer_seeds: &[&[&[u8]]] = &[seeds];

    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.reward_vault.to_account_info(),
            to: ctx.accounts.owner_reward_token.to_account_info(),
            authority: ctx.accounts.pool_auth.to_account_info(),
        },
        signer_seeds,
    );

    token::transfer(cpi_ctx, amount)?;

    staker.pending_rewards = 0;
    staker.refresh_reward_debt(pool)?;

    emit!(StakingRewardClaimed {
        pool: pool.key(),
        staker: staker.key(),
        owner: staker.owner,
        amount,
    });

    Ok(())
}
