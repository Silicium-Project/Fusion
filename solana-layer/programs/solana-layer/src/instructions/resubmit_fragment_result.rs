use anchor_lang::prelude::*;
use anchor_spl::token::TokenAccount;

use crate::{
    constants::MIN_COMPUTE_STAKE,
    error::SiliciumError,
    events::FragmentSubmitted,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        worker::{Worker, WorkerStatus, ROLE_COMPUTE},
    },
};

#[derive(Accounts)]
#[instruction(fragment_index: u32)]
pub struct ResubmitFragmentResult<'info> {
    #[account(mut)]
    pub worker: Signer<'info>,

    #[account(
        mut,
        seeds = [b"worker", worker.key().as_ref()],
        bump = worker_account.bump,
        constraint = worker_account.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_account.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = worker_account.stake_amount >= MIN_COMPUTE_STAKE @ SiliciumError::NotAuthorized
    )]
    pub worker_account: Account<'info, Worker>,

    #[account(
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

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
    pub fragment: Account<'info, Fragment>,

    #[account(
        constraint = worker_token.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Account<'info, TokenAccount>,
}

pub fn handler(
    ctx: Context<ResubmitFragmentResult>,
    fragment_index: u32,
    result_hash: [u8; 32],
    proof_ref: [u8; 32],
) -> Result<()> {
    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );

    let fragment_key = ctx.accounts.fragment.key();

    let f = &mut ctx.accounts.fragment;

    require!(
        f.fragment_index == fragment_index,
        SiliciumError::InvalidParams
    );

    require!(
        f.status == FragmentStatus::Rejected,
        SiliciumError::BadFragmentState
    );

    f.round = f.round.saturating_add(1);
    f.yes_votes = 0;
    f.no_votes = 0;
    f.required_quorum = ctx.accounts.job.fragment_quorum;
    f.voting_deadline_unix = ctx.accounts.job.deadline_unix;

    f.worker = ctx.accounts.worker.key();
    f.worker_token_account = ctx.accounts.worker_token.key();
    f.result_hash = result_hash;
    f.proof_ref = proof_ref;
    f.status = FragmentStatus::Submitted;

    ctx.accounts.worker_account.total_submitted =
        ctx.accounts.worker_account.total_submitted.saturating_add(1);

    emit!(FragmentSubmitted {
        job: f.job,
        fragment: fragment_key,
        fragment_index: f.fragment_index,
        worker: f.worker,
        worker_token_account: f.worker_token_account,
        round: f.round,
        result_hash: f.result_hash,
        proof_ref: f.proof_ref,
        is_resubmission: true,
    });

    Ok(())
}
