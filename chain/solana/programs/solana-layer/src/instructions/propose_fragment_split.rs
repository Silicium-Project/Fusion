use anchor_lang::prelude::*;
use anchor_spl::token::TokenAccount;

use crate::{
    constants::{
        MAX_CHILDREN_PER_SPLIT, SPLIT_MIN_COMPLEXITY, SPLIT_MIN_REPUTATION, SPLIT_MIN_STAKE,
    },
    error::SiliciumError,
    events::{FragmentSplitApproved, FragmentSplitProposed},
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        split_proposal::SplitProposal,
        worker::{meets_minimum_stake, Worker, WorkerStatus, ROLE_COMPUTE},
    },
};

#[derive(Accounts)]
pub struct ProposeFragmentSplit<'info> {
    #[account(mut)]
    pub splitter: Signer<'info>,

    #[account(
        mut,
        seeds = [b"worker", splitter.key().as_ref()],
        bump = splitter_worker.bump,
        constraint = splitter_worker.owner == splitter.key() @ SiliciumError::NotAuthorized,
        constraint = splitter_worker.status == WorkerStatus::Active @ SiliciumError::NotAuthorized,
        constraint = splitter_worker.compute_reputation >= SPLIT_MIN_REPUTATION @ SiliciumError::ComputeReputationTooLow,
        constraint = meets_minimum_stake(splitter_worker.stake_amount, SPLIT_MIN_STAKE) @ SiliciumError::StakeTooLow
    )]
    pub splitter_worker: Box<Account<'info, Worker>>,

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
            &parent_fragment.fragment_index.to_le_bytes()
        ],
        bump = parent_fragment.bump,
        constraint = parent_fragment.job == job.key() @ SiliciumError::InvalidParams
    )]
    pub parent_fragment: Box<Account<'info, Fragment>>,

    #[account(
        init,
        payer = splitter,
        space = SplitProposal::SPACE,
        seeds = [
            b"split_proposal",
            parent_fragment.key().as_ref(),
            &parent_fragment.round.to_le_bytes()
        ],
        bump
    )]
    pub split_proposal: Box<Account<'info, SplitProposal>>,

    #[account(
        constraint = escrow.key() == job.escrow @ SiliciumError::InvalidParams,
        constraint = escrow.mint == job.mint @ SiliciumError::InvalidParams
    )]
    pub escrow: Box<Account<'info, TokenAccount>>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<ProposeFragmentSplit>,
    manifest_hash: [u8; 32],
    child_count: u16,
) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;
    let job = &mut ctx.accounts.job;
    let parent = &mut ctx.accounts.parent_fragment;
    let splitter_worker = &mut ctx.accounts.splitter_worker;

    require!(now <= job.deadline_unix, SiliciumError::JobExpired);
    require!(
        splitter_worker.has_role(ROLE_COMPUTE),
        SiliciumError::MissingComputeRole
    );
    require!(child_count >= 2, SiliciumError::SplitChildLimitExceeded);
    require!(
        child_count <= MAX_CHILDREN_PER_SPLIT,
        SiliciumError::SplitChildLimitExceeded
    );
    require!(parent.is_leaf, SiliciumError::ParentFragmentNotLeaf);
    require!(
        parent.status != FragmentStatus::SplitParent,
        SiliciumError::FragmentAlreadySplit
    );
    require!(
        parent.depth < job.max_fragment_depth,
        SiliciumError::SplitDepthExceeded
    );
    require!(
        parent.complexity_score >= SPLIT_MIN_COMPLEXITY,
        SiliciumError::SplitComplexityTooLow
    );
    require!(
        matches!(
            parent.status,
            FragmentStatus::Claimed | FragmentStatus::Submitted
        ),
        SiliciumError::SplitNotAllowed
    );
    require!(
        parent.assigned_worker == ctx.accounts.splitter.key(),
        SiliciumError::NotAuthorized
    );
    require!(
        manifest_hash != [0u8; 32],
        SiliciumError::InvalidSplitManifest
    );

    let projected_total = job
        .total_fragments_created
        .checked_add(child_count as u32)
        .ok_or(SiliciumError::InvalidParams)?;

    require!(
        projected_total <= job.max_fragments,
        SiliciumError::TooManyFragments
    );

    // The initial escrow reserves the maximum tree budget. Keep this check at
    // the split boundary so a malformed or old quote cannot create work that
    // can never be paid. Outstanding verifier claims remain included.
    let max_leaf_fragments = job.max_leaf_fragments();
    let remaining_compute = (max_leaf_fragments.saturating_sub(job.verified_fragments) as u128)
        .checked_mul(job.reward_per_fragment as u128)
        .ok_or(SiliciumError::InvalidParams)?;
    let remaining_verifier = job
        .verifier_reward_budget
        .checked_sub(job.claimed_verifier_rewards_total)
        .ok_or(SiliciumError::InvalidParams)? as u128;
    let required_reserve = remaining_compute
        .checked_add(remaining_verifier)
        .ok_or(SiliciumError::InvalidParams)?;
    require!(
        ctx.accounts.escrow.amount as u128 >= required_reserve,
        SiliciumError::InsufficientEscrow
    );

    if parent.status == FragmentStatus::Claimed {
        splitter_worker.active_claims = splitter_worker.active_claims.saturating_sub(1);
    }

    parent.status = FragmentStatus::SplitApproved;
    parent.is_leaf = false;
    parent.split_manifest_hash = manifest_hash;
    parent.splitter_worker = ctx.accounts.splitter.key();
    parent.children_count = child_count;

    let proposal = &mut ctx.accounts.split_proposal;
    proposal.job = job.key();
    proposal.parent_fragment = parent.key();
    proposal.splitter_worker = ctx.accounts.splitter.key();
    proposal.manifest_hash = manifest_hash;
    proposal.child_count = child_count;
    // The assigned worker was selected by the mesh's Bayesian delegation
    // score. It may subdivide its own claimed work; no client/web-server
    // signature is needed to keep the network moving.
    proposal.approved = true;
    proposal.rejected = false;
    proposal.created_children = 0;
    proposal.bump = ctx.bumps.split_proposal;

    emit!(FragmentSplitProposed {
        job: job.key(),
        parent_fragment: parent.key(),
        parent_fragment_index: parent.fragment_index,
        proposal: proposal.key(),
        splitter_worker: ctx.accounts.splitter.key(),
        manifest_hash,
        child_count,
        depth: parent.depth,
        complexity_score: parent.complexity_score,
    });

    let new_expected = job
        .expected_fragments
        .saturating_sub(1)
        .checked_add(child_count as u32)
        .ok_or(SiliciumError::InvalidParams)?;
    require!(
        new_expected <= max_leaf_fragments,
        SiliciumError::TooManyFragments
    );
    let max_required_compute = (max_leaf_fragments as u128)
        .checked_mul(job.reward_per_fragment as u128)
        .ok_or(SiliciumError::InvalidParams)?;
    let max_required_verifiers = (max_leaf_fragments as u128)
        .checked_mul(job.fragment_quorum as u128)
        .and_then(|value| value.checked_mul(job.verifier_reward_per_vote as u128))
        .ok_or(SiliciumError::InvalidParams)?;
    require!(
        job.verifier_reward_budget as u128 >= max_required_verifiers,
        SiliciumError::InsufficientVerifierBudget
    );
    require!(
        job.deposited_amount as u128 >= max_required_compute + max_required_verifiers,
        SiliciumError::InsufficientEscrow
    );
    job.expected_fragments = new_expected;
    job.total_fragments_created = projected_total;

    emit!(FragmentSplitApproved {
        job: job.key(),
        parent_fragment: parent.key(),
        parent_fragment_index: parent.fragment_index,
        proposal: proposal.key(),
        authority: ctx.accounts.splitter.key(),
        child_count,
        new_expected_fragments: new_expected,
        total_fragments_created: projected_total,
    });

    Ok(())
}
