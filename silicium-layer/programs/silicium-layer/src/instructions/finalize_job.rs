use anchor_lang::prelude::*;
use anchor_spl::token::{self, CloseAccount, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::{
        job::{Job, JobStatus},
        result::JobResult,
    },
};

pub const URI_MAX_LEN: usize = 128;

#[derive(Accounts)]
pub struct FinalizeJob<'info> {
    #[account(mut)]
    pub client: Signer<'info>,

    #[account(
        mut,
        has_one = client @ SiliciumError::NotAuthorized,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    #[account(
        init,
        payer = client,
        space = JobResult::SPACE,
        seeds = [b"result", job.key().as_ref()],
        bump
    )]
    pub result: Account<'info, JobResult>,

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
    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<FinalizeJob>,
    final_hash: [u8; 32],
    output_uri: Vec<u8>,
) -> Result<()> {

    require!(output_uri.len() <= URI_MAX_LEN, SiliciumError::UriTooLong);

    // Must have all fragments verified
    require!(
        ctx.accounts.job.verified_fragments == ctx.accounts.job.expected_fragments,
        SiliciumError::NotReadyToFinalize
    );

    let r = &mut ctx.accounts.result;
    r.job = ctx.accounts.job.key();
    r.final_hash = final_hash;
    r.uri_len = output_uri.len() as u16;

    let mut buf = [0u8; URI_MAX_LEN];
    buf[..output_uri.len()].copy_from_slice(&output_uri);
    r.uri_bytes = buf;
    r.bump = ctx.bumps.result;

    // Refund remaining escrow
    let remaining = ctx.accounts.escrow.amount;

    if remaining > 0 {
        let job_key = ctx.accounts.job.key();
        let bump = ctx.accounts.job.escrow_auth_bump;
        let seeds: &[&[u8]] = &[b"escrow_auth", job_key.as_ref(), &[bump]];
        let signer_seeds: &[&[&[u8]]] = &[seeds];

        let cpi_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.escrow.to_account_info(),
                to: ctx.accounts.client_token.to_account_info(),
                authority: ctx.accounts.escrow_auth.to_account_info(),
            },
            signer_seeds,
        );

        token::transfer(cpi_ctx, remaining)?;

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
    }

    ctx.accounts.job.status = JobStatus::Finalized;

    Ok(())
}
