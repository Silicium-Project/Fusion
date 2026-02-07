use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::job::{Job, JobStatus},
};

#[derive(Accounts)]
#[instruction(job_id: u64)]
pub struct CreateJob<'info> {
    #[account(mut)]
    pub client: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        init,
        payer = client,
        space = Job::SPACE,
        seeds = [b"job", client.key().as_ref(), &job_id.to_le_bytes()],
        bump
    )]
    pub job: Account<'info, Job>,

    /// CHECK: PDA authority for escrow
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(
        init,
        payer = client,
        token::mint = mint,
        token::authority = escrow_auth
    )]
    pub escrow: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = client_token.owner == client.key(),
        constraint = client_token.mint == mint.key()
    )]
    pub client_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(
    ctx: Context<CreateJob>,
    job_id: u64,
    expected_fragments: u32,
    reward_per_fragment: u64,
    deadline_unix: i64,
) -> Result<()> {
    require!(expected_fragments > 0, SiliciumError::InvalidParams);
    require!(reward_per_fragment > 0, SiliciumError::InvalidParams);

    let now = Clock::get()?.unix_timestamp;
    require!(deadline_unix > now, SiliciumError::InvalidParams);

    let total = (expected_fragments as u128)
        .checked_mul(reward_per_fragment as u128)
        .ok_or(SiliciumError::InvalidParams)? as u64;

    let cpi_ctx = CpiContext::new(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.client_token.to_account_info(),
            to: ctx.accounts.escrow.to_account_info(),
            authority: ctx.accounts.client.to_account_info(),
        },
    );
    token::transfer(cpi_ctx, total)?;

    let job = &mut ctx.accounts.job;
    job.job_id = job_id;
    job.client = ctx.accounts.client.key();
    job.mint = ctx.accounts.mint.key();
    job.escrow = ctx.accounts.escrow.key();
    job.expected_fragments = expected_fragments;
    job.verified_fragments = 0;
    job.reward_per_fragment = reward_per_fragment;
    job.deposited_amount = total;
    job.paid_amount = 0;
    job.deadline_unix = deadline_unix;

    job.status = JobStatus::Open;
    job.verifier_authority = job.client; // MVP
    job.challenge_window_sec = 0;
    job.verified_at_unix = 0;

    job.bump = ctx.bumps.job;
    job.escrow_auth_bump = ctx.bumps.escrow_auth;

    Ok(())
}
