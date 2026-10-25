use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::NetworkUnstakeWithdrawn,
    state::{network_staker::NetworkStaker, staking_pool::StakingPool},
};

#[derive(Accounts)]
pub struct WithdrawUnstaked<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump = pool.bump,
        constraint = pool.mint == mint.key() @ SiliciumError::InvalidParams,
        constraint = pool.stake_vault == stake_vault.key() @ SiliciumError::InvalidParams,
        constraint = pool.authority == pool_auth.key() @ SiliciumError::NotAuthorized
    )]
    pub pool: Account<'info, StakingPool>,

    /// CHECK: PDA authority for stake vault
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
        constraint = stake_vault.key() == pool.stake_vault @ SiliciumError::InvalidParams,
        constraint = stake_vault.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub stake_vault: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = owner_token.owner == owner.key() @ SiliciumError::NotAuthorized,
        constraint = owner_token.mint == mint.key() @ SiliciumError::InvalidParams
    )]
    pub owner_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<WithdrawUnstaked>) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;

    let amount = ctx.accounts.staker.unstake_requested_amount;

    require!(amount > 0, SiliciumError::NothingToWithdraw);

    require!(
        now >= ctx.accounts.staker.unstake_available_at,
        SiliciumError::UnstakeCooldownActive
    );

    require!(
        ctx.accounts.stake_vault.amount >= amount,
        SiliciumError::InsufficientEscrow
    );

    let mint_key = ctx.accounts.mint.key();
    let bump = ctx.accounts.pool.authority_bump;

    let seeds: &[&[u8]] = &[b"staking_pool_auth", mint_key.as_ref(), &[bump]];
    let signer_seeds: &[&[&[u8]]] = &[seeds];

    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.stake_vault.to_account_info(),
            to: ctx.accounts.owner_token.to_account_info(),
            authority: ctx.accounts.pool_auth.to_account_info(),
        },
        signer_seeds,
    );

    token::transfer(cpi_ctx, amount)?;

    ctx.accounts.staker.unstake_requested_amount = 0;
    ctx.accounts.staker.unstake_available_at = 0;

    emit!(NetworkUnstakeWithdrawn {
        pool: ctx.accounts.pool.key(),
        staker: ctx.accounts.staker.key(),
        owner: ctx.accounts.owner.key(),
        amount,
    });

    Ok(())
}
