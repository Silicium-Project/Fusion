use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    events::VerifierRewardClaimed,
    state::{
        fragment::Fragment,
        fragment_resolution::FragmentResolution,
        fragment_vote::FragmentVote,
        job::{Job, JobStatus},
        reputation::{update_verify_reputation, ReputationEvent},
        worker::Worker,
        worker_payout::WorkerPayout,
    },
};

#[derive(Accounts)]
pub struct ClaimVerifierReward<'info> {
    #[account(mut)]
    pub verifier: Signer<'info>,

    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Box<Account<'info, Job>>,

    #[account(
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
        seeds = [
            b"fragment_resolution",
            fragment.key().as_ref(),
            &vote.round.to_le_bytes()
        ],
        bump = round_resolution.bump,
        constraint = round_resolution.fragment == fragment.key() @ SiliciumError::InvalidParams,
        constraint = round_resolution.round == vote.round @ SiliciumError::InvalidParams
    )]
    pub round_resolution: Box<Account<'info, FragmentResolution>>,

    #[account(
        mut,
        seeds = [
            b"fragment_vote",
            fragment.key().as_ref(),
            verifier.key().as_ref(),
            &vote.round.to_le_bytes()
        ],
        bump = vote.bump,
        constraint = vote.fragment == fragment.key() @ SiliciumError::InvalidParams,
        constraint = vote.verifier == verifier.key() @ SiliciumError::NotAuthorized,
        constraint = vote.round == round_resolution.round @ SiliciumError::InvalidParams
    )]
    pub vote: Box<Account<'info, FragmentVote>>,

    #[account(
        mut,
        seeds = [b"worker", verifier.key().as_ref()],
        bump = verifier_worker.bump,
        constraint = verifier_worker.owner == verifier.key() @ SiliciumError::NotAuthorized
    )]
    pub verifier_worker: Box<Account<'info, Worker>>,

    /// CHECK: escrow authority PDA
    #[account(
        seeds = [b"escrow_auth", job.key().as_ref()],
        bump = job.escrow_auth_bump
    )]
    pub escrow_auth: UncheckedAccount<'info>,

    #[account(
        mut,
        constraint = escrow.key() == job.escrow @ SiliciumError::InvalidParams,
        constraint = escrow.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub escrow: Box<Account<'info, TokenAccount>>,

    #[account(
        mut,
        constraint = verifier_token.owner == verifier.key() @ SiliciumError::NotAuthorized,
        constraint = verifier_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub verifier_token: Box<Account<'info, TokenAccount>>,

    #[account(
        seeds = [b"worker_payout", verifier_worker.key().as_ref()],
        bump = verifier_payout.bump,
        constraint = verifier_payout.worker == verifier.key() @ SiliciumError::NotAuthorized
    )]
    pub verifier_payout: Box<Account<'info, WorkerPayout>>,

    #[account(
        mut,
        constraint = verifier_payout_token.owner == verifier_payout.payout_wallet @ SiliciumError::NotAuthorized,
        constraint = verifier_payout_token.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub verifier_payout_token: Box<Account<'info, TokenAccount>>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ClaimVerifierReward>) -> Result<()> {
    let job = &mut ctx.accounts.job;
    let round_resolution = &mut ctx.accounts.round_resolution;
    let vote = &mut ctx.accounts.vote;
    let verifier_worker = &mut ctx.accounts.verifier_worker;

    require!(
        round_resolution.resolved,
        SiliciumError::FragmentNotResolved
    );

    require!(
        vote.round == round_resolution.round,
        SiliciumError::InvalidParams
    );

    require!(
        vote.fragment == ctx.accounts.fragment.key(),
        SiliciumError::InvalidParams
    );

    require!(
        !vote.reward_claimed,
        SiliciumError::RewardAlreadyClaimed
    );

    require!(
        round_resolution.claimed_rewards < round_resolution.eligible_rewards,
        SiliciumError::VoteNotEligibleForReward
    );

    require!(
        vote.choice == round_resolution.winning_choice,
        SiliciumError::VoteNotEligibleForReward
    );

    let reward = job.verifier_reward_per_vote;

    require!(
        ctx.accounts.escrow.amount >= reward,
        SiliciumError::InsufficientEscrow
    );

    let job_key = job.key();
    let bump = job.escrow_auth_bump;
    let seeds: &[&[u8]] = &[b"escrow_auth", job_key.as_ref(), &[bump]];
    let signer_seeds: &[&[&[u8]]] = &[seeds];

    let verifier_reward_account = ctx.accounts.verifier_payout_token.to_account_info();

    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.escrow.to_account_info(),
            to: verifier_reward_account,
            authority: ctx.accounts.escrow_auth.to_account_info(),
        },
        signer_seeds,
    );

    token::transfer(cpi_ctx, reward)?;

    vote.reward_claimed = true;

    round_resolution.claimed_rewards =
        round_resolution.claimed_rewards.saturating_add(1);

    job.claimed_verifier_rewards_total =
        job.claimed_verifier_rewards_total.saturating_add(reward);

    job.paid_amount = job.paid_amount.saturating_add(reward);

    update_verify_reputation(verifier_worker, ReputationEvent::VerificationSuccess);

    emit!(VerifierRewardClaimed {
        job: job.key(),
        fragment: ctx.accounts.fragment.key(),
        verifier: ctx.accounts.verifier.key(),
        vote: vote.key(),
        round: vote.round,
        amount: reward,
        claimed_rewards: round_resolution.claimed_rewards,
        eligible_rewards: round_resolution.eligible_rewards,
    });

    Ok(())
}
