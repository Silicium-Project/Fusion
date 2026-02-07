use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::{
        fragment::{Fragment, FragmentStatus},
        fragment_vote::FragmentVote,
        job::{Job, JobStatus},
        worker::{Worker, WorkerStatus},
    },
};

pub const MIN_VERIFIER_STAKE: u64 = 1; // To change later

#[derive(Accounts)]
pub struct VoteFragment<'info> {
    #[account(mut)]
    pub verifier: Signer<'info>,

    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    #[account(
        mut,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment.fragment_index.to_le_bytes()
        ],
        bump = fragment.bump
    )]
    pub fragment: Account<'info, Fragment>,

    // verifier must be a registered worker (MVP)
    #[account(
        seeds = [b"worker", verifier.key().as_ref()],
        bump = verifier_worker.bump,
        constraint = verifier_worker.owner == verifier.key() @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.stake_amount >= MIN_VERIFIER_STAKE @ SiliciumError::NotAuthorized
    )]
    pub verifier_worker: Account<'info, Worker>,

    // ensures 1 vote per verifier per fragment
    #[account(
        init,
        payer = verifier,
        space = FragmentVote::SPACE,
        seeds = [
            b"fragment_vote",
            fragment.key().as_ref(),
            verifier.key().as_ref()
        ],
        bump
    )]
    pub vote: Account<'info, FragmentVote>,

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
        constraint = worker_token.owner == fragment.worker,
        constraint = worker_token.mint == job.mint
    )]
    pub worker_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<VoteFragment>, choice: bool) -> Result<()> {
    // Fragment must be in Submitted state
    require!(
        ctx.accounts.fragment.status == FragmentStatus::Submitted,
        SiliciumError::BadFragmentState
    );

    // Optional: voting deadline
    let now = Clock::get()?.unix_timestamp;
    require!(
        now <= ctx.accounts.fragment.voting_deadline_unix,
        SiliciumError::JobNotCancellable // (idéalement crée une erreur VotingClosed)
    );

    // record vote
    ctx.accounts.vote.fragment = ctx.accounts.fragment.key();
    ctx.accounts.vote.verifier = ctx.accounts.verifier.key();
    ctx.accounts.vote.choice = choice;
    ctx.accounts.vote.bump = ctx.bumps.vote;

    // count vote
    if choice {
        ctx.accounts.fragment.yes_votes = ctx.accounts.fragment.yes_votes.saturating_add(1);
    } else {
        ctx.accounts.fragment.no_votes = ctx.accounts.fragment.no_votes.saturating_add(1);
    }

    // check quorum reached
    let q = ctx.accounts.fragment.required_quorum;

    if ctx.accounts.fragment.yes_votes >= q {
        // Verified => pay worker once
        let reward = ctx.accounts.job.reward_per_fragment;
        require!(ctx.accounts.escrow.amount >= reward, SiliciumError::InsufficientEscrow);

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
        ctx.accounts.job.verified_fragments = ctx
            .accounts
            .job
            .verified_fragments
            .saturating_add(1);

        ctx.accounts.fragment.status = FragmentStatus::Verified;

        if ctx.accounts.job.verified_fragments == ctx.accounts.job.expected_fragments {
            ctx.accounts.job.verified_at_unix = now;
        }
    } else if ctx.accounts.fragment.no_votes >= q {
        ctx.accounts.fragment.status = FragmentStatus::Rejected;
    }

    Ok(())
}
