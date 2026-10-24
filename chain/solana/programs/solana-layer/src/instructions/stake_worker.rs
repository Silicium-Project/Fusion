use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::WorkerStaked,
    state::worker::{Worker, WorkerStatus},
};

#[derive(Accounts)]
pub struct StakeWorker<'info> {
    #[account(mut)]
    pub worker: Signer<'info>,

    #[account(
        mut,
        seeds = [b"worker", worker.key().as_ref()],
        bump = worker_account.bump,
        constraint = worker_account.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_account.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
    )]
    pub worker_account: Account<'info, Worker>,

    pub mint: Account<'info, Mint>,

    #[account(
        mut,
        constraint = worker_token.owner == worker.key(),
        constraint = worker_token.mint == mint.key(),
    )]
    pub worker_token: Account<'info, TokenAccount>,

    /// CHECK: PDA authority du vault
    #[account(
        seeds = [b"stake_auth", worker_account.key().as_ref()],
        bump
    )]
    pub stake_auth: UncheckedAccount<'info>,

    #[account(
        init_if_needed,
        payer = worker,
        seeds = [b"stake_vault", worker.key().as_ref()],
        bump,
        token::mint = mint,
        token::authority = stake_auth
    )]
    pub stake_vault: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<StakeWorker>, amount: u64) -> Result<()> {
    require!(amount > 0, SiliciumError::InvalidAmount);

    let worker_key = ctx.accounts.worker.key();
    let worker_account_key = ctx.accounts.worker_account.key();
    let mint_key = ctx.accounts.mint.key();
    let stake_vault_key = ctx.accounts.stake_vault.key();

    let w = &mut ctx.accounts.worker_account;

    if w.stake_mint == Pubkey::default() {
        w.stake_mint = mint_key;
        w.stake_vault = stake_vault_key;
    } else {
        require!(w.stake_mint == mint_key, SiliciumError::WrongStakeMint);
        require!(w.stake_vault == stake_vault_key, SiliciumError::WrongStakeVault);
    }

    let cpi_ctx = CpiContext::new(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.worker_token.to_account_info(),
            to: ctx.accounts.stake_vault.to_account_info(),
            authority: ctx.accounts.worker.to_account_info(),
        },
    );

    token::transfer(cpi_ctx, amount)?;

    w.stake_amount = w.stake_amount.saturating_add(amount);

    emit!(WorkerStaked {
        worker: worker_key,
        worker_account: worker_account_key,
        mint: mint_key,
        stake_vault: stake_vault_key,
        amount,
        total_stake: w.stake_amount,
    });

    Ok(())
}
