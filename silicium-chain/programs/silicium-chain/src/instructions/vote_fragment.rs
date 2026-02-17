use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::{
        fragment::{Fragment, FragmentStatus},
        fragment_vote::FragmentVote,
        job::{Job, JobStatus},
        worker::{Worker, WorkerStatus, ROLE_VERIFY},
    },
};

pub const MIN_VERIFIER_STAKE: u64 = 1;

#[derive(Accounts)]
pub struct VoteFragment<'info> {
    /// Verifier wallet
    #[account(mut)]
    pub verifier: Signer<'info>,

    /// Job must be open
    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    /// Fragment being voted
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

    /// Verifier must be registered worker
    #[account(
        mut,
        seeds = [b"worker", verifier.key().as_ref()],
        bump = verifier_worker.bump,
        constraint = verifier_worker.owner == verifier.key() @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.stake_amount >= MIN_VERIFIER_STAKE @ SiliciumError::NotAuthorized
    )]
    pub verifier_worker: Account<'info, Worker>,

    /// Prevent double voting
    #[account(
        init,
        payer = verifier,
        space = FragmentVote::SPACE,
        seeds = [
            b"fragment_vote",
            fragment.key().as_ref(),
            verifier.key().as_ref(),
            &fragment.round.to_le_bytes()
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
        constraint = worker_token.key() == fragment.worker_token_account @ SiliciumError::InvalidParams,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<VoteFragment>, choice: bool) -> Result<()> {
    let fragment = &mut ctx.accounts.fragment;
    let job = &mut ctx.accounts.job;
    let verifier_worker = &mut ctx.accounts.verifier_worker;

    // Fragment must still be pending
    require!(
        fragment.status == FragmentStatus::Submitted,
        SiliciumError::BadFragmentState
    );

    // Prevent self vote
    require!(
        ctx.accounts.verifier.key() != fragment.worker,
        SiliciumError::SelfVoteForbidden
    );

    // Must have VERIFY role
    require!(
        verifier_worker.has_role(ROLE_VERIFY),
        SiliciumError::MissingVerifyRole
    );

    // Voting deadline
    let now = Clock::get()?.unix_timestamp;
    require!(
        now <= fragment.voting_deadline_unix,
        SiliciumError::VotingClosed
    );

    // quorum must be valid
    require!(fragment.required_quorum > 0, SiliciumError::InvalidParams);

    // Record vote
    ctx.accounts.vote.fragment = fragment.key();
    ctx.accounts.vote.verifier = ctx.accounts.verifier.key();
    ctx.accounts.vote.choice = choice;
    ctx.accounts.vote.round = fragment.round;
    ctx.accounts.vote.slashed = false;
    ctx.accounts.vote.bump = ctx.bumps.vote;

    if choice {
        fragment.yes_votes = fragment.yes_votes.saturating_add(1);
    } else {
        fragment.no_votes = fragment.no_votes.saturating_add(1);
    }

    let quorum = fragment.required_quorum;

    // If YES quorum reached
    if fragment.yes_votes >= quorum {
        let reward = job.reward_per_fragment;

        require!(
            ctx.accounts.escrow.amount >= reward,
            SiliciumError::InsufficientEscrow
        );

        // extra safety: prevent overshooting expected fragments
        require!(
            job.verified_fragments < job.expected_fragments,
            SiliciumError::InvalidParams
        );

        // PDA signer seeds
        let job_key = job.key();
        let bump = job.escrow_auth_bump;
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

        // Update job
        job.paid_amount = job.paid_amount.saturating_add(reward);
        job.verified_fragments = job.verified_fragments.saturating_add(1);

        // Mark fragment verified
        fragment.status = FragmentStatus::Verified;

        // Update verifier stats
        verifier_worker.total_verified =
            verifier_worker.total_verified.saturating_add(1);

        if job.verified_fragments == job.expected_fragments {
            job.verified_at_unix = now;
        }
    }
    // If NO quorum reached
    else if fragment.no_votes >= quorum {
        fragment.status = FragmentStatus::Rejected;

        verifier_worker.total_rejected =
            verifier_worker.total_rejected.saturating_add(1);
    }

    Ok(())
}
