use anchor_lang::prelude::*;
use anchor_spl::token::TokenAccount;

use crate::{
    error::SiliciumError,
    events::FragmentClaimed,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        worker::{Worker, WorkerStatus, ROLE_COMPUTE},
    },
};

pub const MIN_COMPUTE_STAKE: u64 = 1;
pub const CLAIM_TTL_SECS: i64 = 5; // test only

#[derive(Accounts)]
#[instruction(fragment_index: u32)]
pub struct ClaimFragment<'info> {
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

pub fn handler(ctx: Context<ClaimFragment>, fragment_index: u32) -> Result<()> {
    require!(
        fragment_index < ctx.accounts.job.expected_fragments,
        SiliciumError::InvalidParams
    );

    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );

    let now = Clock::get()?.unix_timestamp;
    let job_key = ctx.accounts.job.key();
    let fragment_key = ctx.accounts.fragment.key();
    let worker_key = ctx.accounts.worker.key();

    let job = &ctx.accounts.job;
    let f = &mut ctx.accounts.fragment;

    let is_new = f.job == Pubkey::default();

    if is_new {
        f.job = job_key;
        f.fragment_index = fragment_index;
        f.assigned_worker = Pubkey::default();
        f.worker = Pubkey::default();
        f.worker_token_account = Pubkey::default();
        f.result_hash = [0u8; 32];
        f.proof_ref = [0u8; 32];
        f.status = FragmentStatus::Available;
        f.yes_votes = 0;
        f.no_votes = 0;
        f.required_quorum = job.fragment_quorum;
        f.claim_deadline_unix = 0;
        f.voting_deadline_unix = 0;
        f.round = 0;
        f.bump = ctx.bumps.fragment;
    } else {
        require!(f.job == job_key, SiliciumError::InvalidParams);
        require!(f.fragment_index == fragment_index, SiliciumError::InvalidParams);
    }

    match f.status {
        FragmentStatus::Available => {}
        FragmentStatus::Rejected => {
            f.round = f.round.saturating_add(1);
            f.yes_votes = 0;
            f.no_votes = 0;
            f.result_hash = [0u8; 32];
            f.proof_ref = [0u8; 32];
            f.worker = Pubkey::default();
            f.worker_token_account = Pubkey::default();
            f.voting_deadline_unix = 0;
        }
        FragmentStatus::Claimed => {
            require!(
                now > f.claim_deadline_unix,
                SiliciumError::FragmentAlreadyClaimed
            );
        }
        FragmentStatus::Submitted | FragmentStatus::Verified => {
            return err!(SiliciumError::BadFragmentState);
        }
    }

    f.assigned_worker = worker_key;
    f.claim_deadline_unix = now.saturating_add(CLAIM_TTL_SECS);
    f.required_quorum = job.fragment_quorum;
    f.status = FragmentStatus::Claimed;

    emit!(FragmentClaimed {
        job: job_key,
        fragment: fragment_key,
        fragment_index: f.fragment_index,
        worker: worker_key,
        claim_deadline_unix: f.claim_deadline_unix,
        round: f.round,
    });

    Ok(())
}
