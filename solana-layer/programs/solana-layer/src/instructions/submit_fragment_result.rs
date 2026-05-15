use anchor_lang::prelude::*;
use anchor_spl::token::TokenAccount;

use crate::{
    constants::{MIN_COMPUTE_STAKE, VOTING_TTL_SECS},
    error::SiliciumError,
    events::FragmentSubmitted,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        reputation::MIN_COMPUTE_REPUTATION,
        worker::{Worker, WorkerStatus, ROLE_COMPUTE},
    },
};

#[derive(Accounts)]
#[instruction(fragment_index: u32)]
pub struct SubmitFragmentResult<'info> {
    #[account(mut)]
    pub worker: Signer<'info>,

    #[account(
        mut,
        seeds = [b"worker", worker.key().as_ref()],
        bump = worker_account.bump,
        constraint = worker_account.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_account.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = worker_account.stake_amount >= MIN_COMPUTE_STAKE @ SiliciumError::NotAuthorized,
        constraint = worker_account.compute_reputation >= MIN_COMPUTE_REPUTATION @ SiliciumError::ComputeReputationTooLow
    )]
    pub worker_account: Box<Account<'info, Worker>>,

    #[account(
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Box<Account<'info, Job>>,

    #[account(
        mut,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment_index.to_le_bytes()
        ],
        bump = fragment.bump,
        constraint = fragment.job == job.key() @ SiliciumError::InvalidParams,
        constraint = fragment.fragment_index == fragment_index @ SiliciumError::InvalidParams
    )]
    pub fragment: Box<Account<'info, Fragment>>,

    #[account(
        constraint = worker_token.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Box<Account<'info, TokenAccount>>,
}

pub fn handler(
    ctx: Context<SubmitFragmentResult>,
    fragment_index: u32,
    result_hash: [u8; 32],
    proof_ref: [u8; 32],
) -> Result<()> {
    require!(
        fragment_index < ctx.accounts.job.max_fragments,
        SiliciumError::InvalidParams
    );

    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );

    let now = Clock::get()?.unix_timestamp;
    let fragment_key = ctx.accounts.fragment.key();

    require!(
        now <= ctx.accounts.job.deadline_unix,
        SiliciumError::JobExpired
    );

    let f = &mut ctx.accounts.fragment;

    require!(f.is_leaf, SiliciumError::BadFragmentState);

    require!(
        f.status == FragmentStatus::Claimed,
        SiliciumError::FragmentNotClaimed
    );

    require!(
        f.assigned_worker == ctx.accounts.worker.key(),
        SiliciumError::NotAuthorized
    );

    require!(
        now <= f.claim_deadline_unix,
        SiliciumError::ClaimExpired
    );

    f.worker = ctx.accounts.worker.key();
    f.worker_token_account = ctx.accounts.worker_token.key();
    f.result_hash = result_hash;
    f.proof_ref = proof_ref;
    f.status = FragmentStatus::Submitted;

    f.yes_votes = 0;
    f.no_votes = 0;
    f.required_quorum = ctx.accounts.job.fragment_quorum;
    f.voting_deadline_unix = now.saturating_add(VOTING_TTL_SECS);

    ctx.accounts.worker_account.total_submitted =
        ctx.accounts.worker_account.total_submitted.saturating_add(1);

    ctx.accounts.worker_account.active_claims =
        ctx.accounts.worker_account.active_claims.saturating_sub(1);

    emit!(FragmentSubmitted {
        job: f.job,
        fragment: fragment_key,
        fragment_index: f.fragment_index,
        worker: f.worker,
        worker_token_account: f.worker_token_account,
        round: f.round,
        result_hash: f.result_hash,
        proof_ref: f.proof_ref,
        is_resubmission: false,
    });

    Ok(())
}
