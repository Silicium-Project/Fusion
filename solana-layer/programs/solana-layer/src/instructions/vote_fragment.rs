use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::{FragmentRejected, FragmentVerified},
    state::{
        fragment::{Fragment, FragmentStatus},
        fragment_resolution::FragmentResolution,
        fragment_vote::FragmentVote,
        job::{Job, JobStatus},
        reputation::{
            update_compute_reputation, update_compute_reputation_weighted, MIN_VERIFY_REPUTATION,
            ReputationEvent,
        },
        worker_payout::WorkerPayout,
        worker::{Worker, WorkerStatus, ROLE_VERIFY},
    },
};

#[derive(Accounts)]
pub struct VoteFragment<'info> {
    #[account(mut)]
    pub verifier: Signer<'info>,

    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Box<Account<'info, Job>>,

    #[account(
        mut,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment.fragment_index.to_le_bytes()
        ],
        bump = fragment.bump,
        constraint = fragment.job == job.key() @ SiliciumError::InvalidParams
    )]
    pub fragment: Box<Account<'info, Fragment>>,

    #[account(
        mut,
        seeds = [b"worker", verifier.key().as_ref()],
        bump = verifier_worker.bump,
        constraint = verifier_worker.owner == verifier.key() @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = verifier_worker.verify_reputation >= MIN_VERIFY_REPUTATION @ SiliciumError::VerifierReputationTooLow
    )]
    pub verifier_worker: Box<Account<'info, Worker>>,

    #[account(
        mut,
        seeds = [b"worker", fragment.worker.as_ref()],
        bump = compute_worker.bump,
        constraint = compute_worker.owner == fragment.worker @ SiliciumError::NotAuthorized
    )]
    pub compute_worker: Box<Account<'info, Worker>>,

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
    pub vote: Box<Account<'info, FragmentVote>>,

    #[account(
        init_if_needed,
        payer = verifier,
        space = FragmentResolution::SPACE,
        seeds = [
            b"fragment_resolution",
            fragment.key().as_ref(),
            &fragment.round.to_le_bytes()
        ],
        bump
    )]
    pub round_resolution: Box<Account<'info, FragmentResolution>>,

    /// CHECK: escrow authority PDA
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump = job.escrow_auth_bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(mut, constraint = escrow.key() == job.escrow)]
    pub escrow: Box<Account<'info, TokenAccount>>,

    #[account(
        mut,
        constraint = worker_token.key() == fragment.worker_token_account @ SiliciumError::InvalidParams,
        constraint = worker_token.owner == fragment.worker @ SiliciumError::NotAuthorized,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Box<Account<'info, TokenAccount>>,

    #[account(
        seeds = [b"worker_payout", compute_worker.key().as_ref()],
        bump = worker_payout.bump,
        constraint = worker_payout.worker == fragment.worker @ SiliciumError::NotAuthorized
    )]
    pub worker_payout: Box<Account<'info, WorkerPayout>>,

    #[account(
        mut,
        constraint = worker_payout_token.owner == worker_payout.payout_wallet @ SiliciumError::NotAuthorized,
        constraint = worker_payout_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_payout_token: Box<Account<'info, TokenAccount>>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<VoteFragment>, choice: bool) -> Result<()> {
    let fragment = &mut ctx.accounts.fragment;
    let job = &mut ctx.accounts.job;
    let verifier_worker = &mut ctx.accounts.verifier_worker;
    let compute_worker = &mut ctx.accounts.compute_worker;
    let round_resolution = &mut ctx.accounts.round_resolution;

    require!(
        fragment.job == job.key(),
        SiliciumError::InvalidParams
    );

    require!(
        fragment.is_leaf,
        SiliciumError::BadFragmentState
    );

    require!(
        fragment.status == FragmentStatus::Submitted,
        SiliciumError::BadFragmentState
    );

    require!(
        ctx.accounts.verifier.key() != fragment.worker,
        SiliciumError::SelfVoteForbidden
    );

    require!(
        ctx.accounts.verifier.key() != job.client,
        SiliciumError::ClientCannotVerifyOwnJob
    );

    require!(
        verifier_worker.has_role(ROLE_VERIFY),
        SiliciumError::MissingVerifyRole
    );

    require!(
        compute_worker.owner == fragment.worker,
        SiliciumError::NotAuthorized
    );

    require!(
        fragment.worker_token_account == ctx.accounts.worker_token.key(),
        SiliciumError::InvalidParams
    );

    let now = Clock::get()?.unix_timestamp;

    require!(
        now <= fragment.voting_deadline_unix,
        SiliciumError::VotingClosed
    );

    require!(
        now <= job.deadline_unix,
        SiliciumError::JobExpired
    );

    require!(
        fragment.required_quorum > 0,
        SiliciumError::InvalidParams
    );

    if round_resolution.fragment == Pubkey::default() {
        round_resolution.fragment = fragment.key();
        round_resolution.round = fragment.round;
        round_resolution.resolved = false;
        round_resolution.winning_choice = false;
        round_resolution.eligible_rewards = 0;
        round_resolution.claimed_rewards = 0;
        round_resolution.bump = ctx.bumps.round_resolution;
    } else {
        require!(
            round_resolution.fragment == fragment.key(),
            SiliciumError::InvalidParams
        );

        require!(
            round_resolution.round == fragment.round,
            SiliciumError::InvalidParams
        );
    }

    require!(
        !round_resolution.resolved,
        SiliciumError::BadFragmentState
    );

    ctx.accounts.vote.fragment = fragment.key();
    ctx.accounts.vote.verifier = ctx.accounts.verifier.key();
    ctx.accounts.vote.choice = choice;
    ctx.accounts.vote.round = fragment.round;
    ctx.accounts.vote.slashed = false;
    ctx.accounts.vote.reward_claimed = false;
    ctx.accounts.vote.bump = ctx.bumps.vote;

    if choice {
        fragment.yes_votes = fragment.yes_votes.saturating_add(1);
    } else {
        fragment.no_votes = fragment.no_votes.saturating_add(1);
    }

    let quorum = fragment.required_quorum;

    let round_verifier_claimable = (quorum as u64)
        .checked_mul(job.verifier_reward_per_vote)
        .ok_or(SiliciumError::InvalidParams)?;

    if fragment.yes_votes >= quorum {
        let next_claimable_total = job
            .claimable_verifier_rewards_total
            .checked_add(round_verifier_claimable)
            .ok_or(SiliciumError::InvalidParams)?;

        require!(
            next_claimable_total <= job.verifier_reward_budget,
            SiliciumError::InsufficientVerifierBudget
        );

        let worker_reward = job.reward_per_fragment;

        let total_needed_now = worker_reward
            .checked_add(round_verifier_claimable)
            .ok_or(SiliciumError::InvalidParams)?;

        require!(
            ctx.accounts.escrow.amount >= total_needed_now,
            SiliciumError::InsufficientEscrow
        );

        require!(
            job.verified_fragments < job.expected_fragments,
            SiliciumError::InvalidParams
        );

        let job_key = job.key();
        let bump = job.escrow_auth_bump;
        let seeds: &[&[u8]] = &[b"escrow_auth", job_key.as_ref(), &[bump]];
        let signer_seeds: &[&[&[u8]]] = &[seeds];

        let worker_reward_account = ctx.accounts.worker_payout_token.to_account_info();

        let worker_transfer_ctx = CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.escrow.to_account_info(),
                to: worker_reward_account,
                authority: ctx.accounts.escrow_auth.to_account_info(),
            },
            signer_seeds,
        );

        token::transfer(worker_transfer_ctx, worker_reward)?;

        job.paid_amount = job.paid_amount.saturating_add(worker_reward);
        job.claimable_verifier_rewards_total = next_claimable_total;
        job.verified_fragments = job.verified_fragments.saturating_add(1);

        fragment.status = FragmentStatus::Verified;

        round_resolution.resolved = true;
        round_resolution.winning_choice = true;
        round_resolution.eligible_rewards = quorum;
        round_resolution.claimed_rewards = 0;

        update_compute_reputation(compute_worker, ReputationEvent::ComputeSuccess);

        if job.verified_fragments == job.expected_fragments {
            job.verified_at_unix = now;
        }

        emit!(FragmentVerified {
            job: job.key(),
            fragment: fragment.key(),
            fragment_index: fragment.fragment_index,
            worker: fragment.worker,
            verifier: ctx.accounts.verifier.key(),
            worker_reward,
            verifier_reward_per_vote: job.verifier_reward_per_vote,
            eligible_verifier_rewards: quorum,
            yes_votes: fragment.yes_votes,
            round: fragment.round,
            verified_fragments: job.verified_fragments,
            expected_fragments: job.expected_fragments,
        });
    } else if fragment.no_votes >= quorum {
        // The quote reserves exactly one compute reward plus the successful
        // quorum's verifier rewards per payable leaf. A rejected attempt is
        // not paid, so retries cannot consume the fixed escrow before a valid
        // result reaches quorum.
        fragment.status = FragmentStatus::Rejected;

        round_resolution.resolved = true;
        round_resolution.winning_choice = false;
        round_resolution.eligible_rewards = 0;
        round_resolution.claimed_rewards = 0;

        update_compute_reputation_weighted(
            compute_worker,
            ReputationEvent::MajorComputeError,
            verifier_worker.verify_reputation,
        );

        emit!(FragmentRejected {
            job: job.key(),
            fragment: fragment.key(),
            fragment_index: fragment.fragment_index,
            worker: fragment.worker,
            verifier: ctx.accounts.verifier.key(),
            verifier_reward_per_vote: job.verifier_reward_per_vote,
            eligible_verifier_rewards: 0,
            no_votes: fragment.no_votes,
            round: fragment.round,
        });
    }

    Ok(())
}
