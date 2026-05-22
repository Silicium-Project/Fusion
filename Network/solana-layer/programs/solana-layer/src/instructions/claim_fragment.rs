use anchor_lang::prelude::*;
use anchor_spl::token::TokenAccount;

use crate::{
    constants::MAX_ACTIVE_CLAIMS_PER_WORKER,
    error::SiliciumError,
    events::FragmentClaimed,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        reputation::MIN_COMPUTE_REPUTATION,
        worker::{Worker, WorkerStatus, ROLE_COMPUTE},
    },
};

pub const DEFAULT_ROOT_REQUIRED_STAKE: u64 = 0;
pub const CLAIM_TTL_SECS: i64 = 5;
pub const DEFAULT_ROOT_REQUIRED_REPUTATION: i64 = MIN_COMPUTE_REPUTATION;
pub const DEFAULT_ROOT_COMPLEXITY_SCORE: u32 = 1_000;
pub const DEFAULT_MAX_CHILDREN: u16 = 8;

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
        constraint = worker_account.compute_reputation >= MIN_COMPUTE_REPUTATION @ SiliciumError::ComputeReputationTooLow
    )]
    pub worker_account: Box<Account<'info, Worker>>,

    #[account(
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Box<Account<'info, Job>>,

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
    pub fragment: Box<Account<'info, Fragment>>,

    #[account(
        constraint = worker_token.owner == worker.key() @ SiliciumError::NotAuthorized,
        constraint = worker_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub worker_token: Box<Account<'info, TokenAccount>>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<ClaimFragment>, fragment_index: u32) -> Result<()> {
    require!(fragment_index < ctx.accounts.job.max_fragments, SiliciumError::InvalidParams);

    require!(
        ctx.accounts.worker_account.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );

    require!(
        ctx.accounts.worker_account.active_claims < MAX_ACTIVE_CLAIMS_PER_WORKER,
        SiliciumError::TooManyActiveClaims
    );

    let now = Clock::get()?.unix_timestamp;
    let job_key = ctx.accounts.job.key();
    let fragment_key = ctx.accounts.fragment.key();
    let worker_key = ctx.accounts.worker.key();

    let f = &mut ctx.accounts.fragment;
    let is_new = f.job == Pubkey::default();

    if is_new {
        // Lazy root fragment creation. Child/sub-fragments are created by create_sub_fragment.
        require!(
            fragment_index < ctx.accounts.job.expected_fragments,
            SiliciumError::InvalidParams
        );

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
        f.required_quorum = ctx.accounts.job.fragment_quorum;
        f.claim_deadline_unix = 0;
        f.voting_deadline_unix = 0;
        f.round = 0;

        f.parent_fragment = Pubkey::default();
        f.depth = 0;
        f.children_count = 0;
        f.max_children = DEFAULT_MAX_CHILDREN;
        f.split_manifest_hash = [0u8; 32];
        f.splitter_worker = Pubkey::default();
        f.is_leaf = true;
        f.required_compute_reputation = DEFAULT_ROOT_REQUIRED_REPUTATION;
        f.required_stake = DEFAULT_ROOT_REQUIRED_STAKE;
        f.complexity_score = DEFAULT_ROOT_COMPLEXITY_SCORE;

        f.bump = ctx.bumps.fragment;
    } else {
        require!(f.job == job_key, SiliciumError::InvalidParams);
        require!(f.fragment_index == fragment_index, SiliciumError::InvalidParams);
    }

    require!(f.is_leaf, SiliciumError::BadFragmentState);

    match f.status {
        FragmentStatus::Available => {}
        FragmentStatus::Rejected => {
            // Backward-compatible V1 flow: a rejected fragment can be claimed again,
            // then submitted with submit_fragment_result.
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
            require!(now > f.claim_deadline_unix, SiliciumError::FragmentAlreadyClaimed);
        }
        _ => {
            return err!(SiliciumError::BadFragmentState);
        }
    }

    require!(
        ctx.accounts.worker_account.compute_reputation >= f.required_compute_reputation,
        SiliciumError::ComputeReputationTooLow
    );
    require!(
        ctx.accounts.worker_account.stake_amount >= f.required_stake,
        SiliciumError::StakeTooLow
    );
    require!(now <= ctx.accounts.job.deadline_unix, SiliciumError::JobExpired);

    f.assigned_worker = worker_key;
    f.worker = Pubkey::default();
    f.worker_token_account = ctx.accounts.worker_token.key();
    f.status = FragmentStatus::Claimed;
    f.claim_deadline_unix = now.saturating_add(CLAIM_TTL_SECS);
    f.required_quorum = ctx.accounts.job.fragment_quorum;
    f.yes_votes = 0;
    f.no_votes = 0;

    ctx.accounts.worker_account.active_claims =
        ctx.accounts.worker_account.active_claims.saturating_add(1);

    emit!(FragmentClaimed {
        job: f.job,
        fragment: fragment_key,
        fragment_index: f.fragment_index,
        worker: worker_key,
        worker_token_account: ctx.accounts.worker_token.key(),
        claim_deadline_unix: f.claim_deadline_unix,
        round: f.round,
    });

    Ok(())
}
