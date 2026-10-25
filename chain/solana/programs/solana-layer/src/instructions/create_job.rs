use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{
    constants::{
        DEFAULT_MAX_FRAGMENT_DEPTH, DEFAULT_MAX_FRAGMENT_MULTIPLIER, MAX_FRAGMENTS_PER_JOB,
        MAX_FRAGMENT_QUORUM, MAX_JOB_TTL_SECS, MIN_FRAGMENT_QUORUM, MIN_JOB_DEPOSIT,
        MIN_JOB_TTL_SECS,
    },
    error::SiliciumError,
    events::JobCreated,
    state::job::{Job, JobStatus},
};

#[derive(Accounts)]
#[instruction(job_id: u64)]
pub struct CreateJob<'info> {
    #[account(mut)]
    pub client: Signer<'info>,

    pub mint: Account<'info, Mint>,

    #[account(
        init,
        payer = client,
        space = Job::SPACE,
        seeds = [b"job", client.key().as_ref(), &job_id.to_le_bytes()],
        bump
    )]
    pub job: Account<'info, Job>,

    /// CHECK: PDA authority for escrow
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(
        init,
        payer = client,
        token::mint = mint,
        token::authority = escrow_auth
    )]
    pub escrow: Account<'info, TokenAccount>,

    #[account(
        mut,
        constraint = client_token.owner == client.key(),
        constraint = client_token.mint == mint.key()
    )]
    pub client_token: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

// Preserve the positional arguments of the existing on-chain instruction ABI.
#[allow(clippy::too_many_arguments)]
pub fn handler(
    ctx: Context<CreateJob>,
    job_id: u64,
    expected_fragments: u32,
    reward_per_fragment: u64,
    verifier_reward_per_vote: u64,
    verifier_reward_budget: u64,
    deadline_unix: i64,
    fragment_quorum: u16,
) -> Result<()> {
    require!(expected_fragments > 0, SiliciumError::InvalidParams);

    require!(
        expected_fragments <= MAX_FRAGMENTS_PER_JOB,
        SiliciumError::TooManyFragments
    );

    require!(reward_per_fragment > 0, SiliciumError::InvalidParams);

    require!(
        fragment_quorum >= MIN_FRAGMENT_QUORUM,
        SiliciumError::InvalidParams
    );

    require!(
        fragment_quorum <= MAX_FRAGMENT_QUORUM,
        SiliciumError::InvalidParams
    );

    let now = Clock::get()?.unix_timestamp;
    let ttl = deadline_unix.saturating_sub(now);

    require!(ttl >= MIN_JOB_TTL_SECS, SiliciumError::InvalidDeadline);
    require!(ttl <= MAX_JOB_TTL_SECS, SiliciumError::InvalidDeadline);

    // `max_fragments` reserves account indices for the entire binary tree,
    // including internal split nodes. The escrow reserve below is based on
    // the smaller maximum payable leaf count.
    let max_fragments = MAX_FRAGMENTS_PER_JOB.max(expected_fragments);
    let child_slots_per_root =
        max_fragments.saturating_sub(expected_fragments) / expected_fragments;
    let max_leaf_fragments = expected_fragments
        .saturating_mul(1 + child_slots_per_root / 2)
        .min(expected_fragments.saturating_mul(DEFAULT_MAX_FRAGMENT_MULTIPLIER))
        .min(MAX_FRAGMENTS_PER_JOB);

    let verifier_needed_u128 = (max_leaf_fragments as u128)
        .checked_mul(fragment_quorum as u128)
        .ok_or(SiliciumError::InvalidParams)?
        .checked_mul(verifier_reward_per_vote as u128)
        .ok_or(SiliciumError::InvalidParams)?;

    require!(
        verifier_reward_budget as u128 >= verifier_needed_u128,
        SiliciumError::InsufficientVerifierBudget
    );

    let worker_total_u128 = (max_leaf_fragments as u128)
        .checked_mul(reward_per_fragment as u128)
        .ok_or(SiliciumError::InvalidParams)?;

    let total_u128 = worker_total_u128
        .checked_add(verifier_reward_budget as u128)
        .ok_or(SiliciumError::InvalidParams)?;

    require!(total_u128 <= u64::MAX as u128, SiliciumError::InvalidParams);

    let total = total_u128 as u64;
    require!(total >= MIN_JOB_DEPOSIT, SiliciumError::DepositTooSmall);

    let cpi_ctx = CpiContext::new(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.client_token.to_account_info(),
            to: ctx.accounts.escrow.to_account_info(),
            authority: ctx.accounts.client.to_account_info(),
        },
    );

    token::transfer(cpi_ctx, total)?;

    let job = &mut ctx.accounts.job;

    job.job_id = job_id;
    job.client = ctx.accounts.client.key();
    job.mint = ctx.accounts.mint.key();
    job.escrow = ctx.accounts.escrow.key();

    // V2: expected_fragments = nombre de fragments leaf attendus.
    job.expected_fragments = expected_fragments;
    job.verified_fragments = 0;

    job.reward_per_fragment = reward_per_fragment;
    job.verifier_reward_per_vote = verifier_reward_per_vote;
    job.verifier_reward_budget = verifier_reward_budget;

    job.deposited_amount = total;
    job.paid_amount = 0;

    job.claimable_verifier_rewards_total = 0;
    job.claimed_verifier_rewards_total = 0;

    job.created_at_unix = now;
    job.deadline_unix = deadline_unix;
    job.verified_at_unix = 0;

    job.fragment_quorum = fragment_quorum;

    job.max_fragments = max_fragments;
    job.total_fragments_created = expected_fragments;
    job.max_fragment_depth = DEFAULT_MAX_FRAGMENT_DEPTH;
    job.split_authority = ctx.accounts.client.key();

    job.status = JobStatus::Open;

    job.bump = ctx.bumps.job;
    job.escrow_auth_bump = ctx.bumps.escrow_auth;

    emit!(JobCreated {
        job: job.key(),
        client: job.client,
        mint: job.mint,
        escrow: job.escrow,
        job_id: job.job_id,
        expected_fragments: job.expected_fragments,
        reward_per_fragment: job.reward_per_fragment,
        verifier_reward_per_vote: job.verifier_reward_per_vote,
        verifier_reward_budget: job.verifier_reward_budget,
        deposited_amount: job.deposited_amount,
        deadline_unix: job.deadline_unix,
        fragment_quorum: job.fragment_quorum,
    });

    Ok(())
}
