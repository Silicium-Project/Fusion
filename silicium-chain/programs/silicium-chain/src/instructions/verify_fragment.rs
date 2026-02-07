use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::Job,
    },
};

#[derive(Accounts)]
pub struct VerifyFragment<'info> {
    /// Vérificateur (MVP: le client)
    pub verifier: Signer<'info>,

    #[account(
        mut,
        constraint = !job.is_finalized @ SiliciumError::JobFinalized,
        has_one = client @ SiliciumError::NotAuthorized
    )]
    pub job: Account<'info, Job>,

    /// CHECK: juste utilisé pour has_one / contrôle
    pub client: UncheckedAccount<'info>,

    #[account(mut)]
    pub fragment: Account<'info, Fragment>,

    /// CHECK: PDA authority of escrow token account
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump = job.escrow_auth_bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(mut, constraint = escrow.key() == job.escrow)]
    pub escrow: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = worker_token.owner == fragment.worker,
        constraint = worker_token.mint == job.mint
    )]
    pub worker_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<VerifyFragment>, verdict: bool) -> Result<()> {
    // verifier doit être le client (MVP)
    require!(
        ctx.accounts.verifier.key() == ctx.accounts.job.client,
        SiliciumError::NotAuthorized
    );

    require!(
        ctx.accounts.fragment.job == ctx.accounts.job.key(),
        SiliciumError::InvalidParams
    );

    require!(
        ctx.accounts.fragment.status == FragmentStatus::Submitted,
        SiliciumError::BadFragmentState
    );

    if verdict {
        let reward = ctx.accounts.job.reward_per_fragment;
        require!(ctx.accounts.escrow.amount >= reward, SiliciumError::InsufficientEscrow);

        // signer seeds (pas de temporaire)
        let job_key = ctx.accounts.job.key();
        let bump = ctx.accounts.job.escrow_auth_bump;
        let seeds: &[&[u8]] = &[b"escrow_auth", job_key.as_ref(), &[bump]];
        let signer_seeds: &[&[&[u8]]] = &[seeds];

        let cpi_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.escrow.to_account_info(),
                to: ctx.accounts.worker_token.to_account_info(),
                authority: ctx.accounts.escrow_auth.to_account_info(),
            },
            signer_seeds,
        );
        token::transfer(cpi_ctx, reward)?;

        ctx.accounts.job.paid_amount = ctx.accounts.job.paid_amount.saturating_add(reward);
        ctx.accounts.job.verified_fragments = ctx.accounts.job.verified_fragments.saturating_add(1);

        ctx.accounts.fragment.status = FragmentStatus::Verified;
    } else {
        ctx.accounts.fragment.status = FragmentStatus::Rejected;
    }

    Ok(())
}
