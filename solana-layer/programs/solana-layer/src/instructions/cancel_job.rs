use anchor_lang::prelude::*;
use anchor_spl::token::{self, CloseAccount, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::JobCancelled,
    state::job::{Job, JobStatus},
};

#[derive(Accounts)]
pub struct CancelJob<'info> {
    #[account(mut)]
    pub client: Signer<'info>,

    #[account(
        mut,
        has_one = client @ SiliciumError::NotAuthorized,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    /// CHECK: escrow authority PDA
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump = job.escrow_auth_bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(mut, constraint = escrow.key() == job.escrow)]
    pub escrow: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = client_token.owner == client.key(),
        constraint = client_token.mint == job.mint
    )]
    pub client_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<CancelJob>) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;

    let nothing_started =
        ctx.accounts.job.verified_fragments == 0 && ctx.accounts.job.paid_amount == 0;
    let deadline_passed = now > ctx.accounts.job.deadline_unix;

    require!(nothing_started || deadline_passed, SiliciumError::JobNotCancellable);

    let job_key = ctx.accounts.job.key();
    let bump = ctx.accounts.job.escrow_auth_bump;
    let seeds: &[&[u8]] = &[b"escrow_auth", job_key.as_ref(), &[bump]];
    let signer_seeds: &[&[&[u8]]] = &[seeds];

    let remaining = ctx.accounts.escrow.amount;

    if remaining > 0 {
        let transfer_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.escrow.to_account_info(),
                to: ctx.accounts.client_token.to_account_info(),
                authority: ctx.accounts.escrow_auth.to_account_info(),
            },
            signer_seeds,
        );
        token::transfer(transfer_ctx, remaining)?;
    }

    let close_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        CloseAccount {
            account: ctx.accounts.escrow.to_account_info(),
            destination: ctx.accounts.client.to_account_info(),
            authority: ctx.accounts.escrow_auth.to_account_info(),
        },
        signer_seeds,
    );
    token::close_account(close_ctx)?;

    ctx.accounts.job.status = JobStatus::Cancelled;

    emit!(JobCancelled {
        job: ctx.accounts.job.key(),
        client: ctx.accounts.client.key(),
        refunded_amount: remaining,
    });

    Ok(())
}
