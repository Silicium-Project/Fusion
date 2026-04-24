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
pub struct SubmitFragmentResult<'info> {
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
        init_if_needed,
        payer = worker,
        space = Fragment::SPACE,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment_index.to_le_bytes()
        ],
        bump
    )]
    pub fragment: Account<'info, Fragment>,

    #[account(
        constraint = worker_token.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Account<'info, TokenAccount>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<SubmitFragmentResult>,
    fragment_index: u32,
    result_hash: [u8; 32],
    proof_ref: [u8; 32],
) -> Result<()> {
    require!(
        fragment_index < ctx.accounts.job.expected_fragments,
        SiliciumError::InvalidParams
    );

    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );

    let f = &mut ctx.accounts.fragment;
    let is_new = f.job == Pubkey::default();

    if !is_new {
        require!(f.job == ctx.accounts.job.key(), SiliciumError::InvalidParams);
        require!(
            f.status == FragmentStatus::Submitted,
            SiliciumError::BadFragmentState
        );
        require!(f.worker == ctx.accounts.worker.key(), SiliciumError::NotAuthorized);
    }

    if is_new {
        require!(
            ctx.accounts.job.fragment_quorum > 0,
            SiliciumError::InvalidParams
        );

        f.yes_votes = 0;
        f.no_votes = 0;
        f.round = 0;
        f.required_quorum = ctx.accounts.job.fragment_quorum;
        f.voting_deadline_unix = ctx.accounts.job.deadline_unix;
    }

    f.job = ctx.accounts.job.key();
    f.fragment_index = fragment_index;
    f.worker = ctx.accounts.worker.key();
    f.worker_token_account = ctx.accounts.worker_token.key();
    f.result_hash = result_hash;
    f.proof_ref = proof_ref;
    f.status = FragmentStatus::Submitted;
    f.bump = ctx.bumps.fragment;

    ctx.accounts.worker_account.total_submitted =
        ctx.accounts.worker_account.total_submitted.saturating_add(1);

    emit!(FragmentSubmitted {
        job: f.job,
        fragment: f.key(),
        fragment_index: f.fragment_index,
        worker: f.worker,
        worker_token_account: f.worker_token_account,
        round: f.round,
        result_hash: f.result_hash,
        proof_ref: f.proof_ref,
    });

    Ok(())
}
