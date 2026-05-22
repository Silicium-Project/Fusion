use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

use crate::{
    events::StakingPoolInitialized,
    state::staking_pool::StakingPool,
};

#[derive(Accounts)]
pub struct InitStakingPool<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        init,
        payer = payer,
        space = StakingPool::SPACE,
        seeds = [b"staking_pool", mint.key().as_ref()],
        bump
    )]
    pub pool: Account<'info, StakingPool>,

    /// CHECK: PDA authority for stake and reward vaults
    #[account(
        seeds = [b"staking_pool_auth", mint.key().as_ref()],
        bump
    )]
    pub pool_auth: UncheckedAccount<'info>,

    #[account(
        init,
        payer = payer,
        token::mint = mint,
        token::authority = pool_auth
    )]
    pub stake_vault: Account<'info, TokenAccount>,

    #[account(
        init,
        payer = payer,
        token::mint = mint,
        token::authority = pool_auth
    )]
    pub reward_vault: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<InitStakingPool>) -> Result<()> {
    let pool = &mut ctx.accounts.pool;

    pool.mint = ctx.accounts.mint.key();
    pool.authority = ctx.accounts.pool_auth.key();
    pool.stake_vault = ctx.accounts.stake_vault.key();
    pool.reward_vault = ctx.accounts.reward_vault.key();

    pool.total_staked = 0;
    pool.acc_reward_per_share = 0;

    pool.bump = ctx.bumps.pool;
    pool.authority_bump = ctx.bumps.pool_auth;

    emit!(StakingPoolInitialized {
        pool: pool.key(),
        mint: pool.mint,
        authority: pool.authority,
        stake_vault: pool.stake_vault,
        reward_vault: pool.reward_vault,
    });

    Ok(())
}
