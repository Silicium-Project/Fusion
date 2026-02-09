use anchor_lang::prelude::*;

use crate::{
    error::SiliciumError,
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

    // Worker registry PDA (1 wallet = 1 Worker account)
    #[account(
        mut,
        seeds = [b"worker", worker.key().as_ref()],
        bump = worker_account.bump,
        constraint = worker_account.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_account.status == WorkerStatus::Active @ SiliciumError::NotAuthorized
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

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<SubmitFragmentResult>,
    fragment_index: u32,
    result_hash: [u8; 32],
    proof_ref: [u8; 32],) -> Result<()> {
    require!(
        fragment_index < ctx.accounts.job.expected_fragments,
        SiliciumError::InvalidParams
    );
    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );
    let f = &mut ctx.accounts.fragment;

    // Detect first initialization
    let is_new = f.job == Pubkey::default();

    // anti-overwrite checks (only if already initialized)
    if !is_new {
        require!(f.job == ctx.accounts.job.key(), SiliciumError::InvalidParams);
        require!(
            f.status != FragmentStatus::Verified,
            SiliciumError::BadFragmentState
        );

        // If already submitted, only the same worker may overwrite (anti-grief)
        if f.status == FragmentStatus::Submitted {
            require!(f.worker == ctx.accounts.worker.key(), SiliciumError::NotAuthorized);
        }
    }

    // 🔑 INIT VOTING FIELDS (only once)
    if is_new {
        f.yes_votes = 0;
        f.no_votes = 0;
        f.required_quorum = 2; // Test quorum
        f.voting_deadline_unix = ctx.accounts.job.deadline_unix;
    }

    // write fragment
    f.job = ctx.accounts.job.key();
    f.fragment_index = fragment_index;
    f.worker = ctx.accounts.worker.key();
    f.result_hash = result_hash;
    f.proof_ref = proof_ref;
    f.status = FragmentStatus::Submitted;
    f.bump = ctx.bumps.fragment;

    // update worker stats
    ctx.accounts.worker_account.total_submitted =
        ctx.accounts.worker_account.total_submitted.saturating_add(1);

    Ok(())
}
