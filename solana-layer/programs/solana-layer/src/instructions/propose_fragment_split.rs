use anchor_lang::prelude::*;

use crate::{
    constants::{MAX_CHILDREN_PER_SPLIT, SPLIT_MIN_COMPLEXITY, SPLIT_MIN_REPUTATION, SPLIT_MIN_STAKE},
    error::SiliciumError,
    events::FragmentSplitProposed,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        split_proposal::SplitProposal,
        worker::{Worker, WorkerStatus, ROLE_COMPUTE},
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
        constraint = splitter_worker.reputation >= SPLIT_MIN_REPUTATION @ SiliciumError::ReputationTooLow,
        constraint = splitter_worker.stake_amount >= SPLIT_MIN_STAKE @ SiliciumError::StakeTooLow
    )]
    pub splitter_worker: Account<'info, Worker>,

    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

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
    pub parent_fragment: Account<'info, Fragment>,

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
    pub split_proposal: Account<'info, SplitProposal>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<ProposeFragmentSplit>,
    manifest_hash: [u8; 32],
    child_count: u16,
) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;
    let job = &ctx.accounts.job;
    let parent = &mut ctx.accounts.parent_fragment;
    let splitter_worker = &mut ctx.accounts.splitter_worker;

    require!(now <= job.deadline_unix, SiliciumError::JobExpired);
    require!(splitter_worker.has_role(ROLE_COMPUTE), SiliciumError::MissingComputeRole);
    require!(child_count >= 2, SiliciumError::SplitChildLimitExceeded);
    require!(child_count <= MAX_CHILDREN_PER_SPLIT, SiliciumError::SplitChildLimitExceeded);
    require!(parent.is_leaf, SiliciumError::ParentFragmentNotLeaf);
    require!(parent.status != FragmentStatus::SplitParent, SiliciumError::FragmentAlreadySplit);
    require!(parent.depth < job.max_fragment_depth, SiliciumError::SplitDepthExceeded);
    require!(parent.complexity_score >= SPLIT_MIN_COMPLEXITY, SiliciumError::SplitComplexityTooLow);
    require!(
        matches!(parent.status, FragmentStatus::Claimed | FragmentStatus::Submitted),
        SiliciumError::SplitNotAllowed
    );
    require!(parent.assigned_worker == ctx.accounts.splitter.key(), SiliciumError::NotAuthorized);
    require!(manifest_hash != [0u8; 32], SiliciumError::InvalidSplitManifest);

    let projected_total = job
        .total_fragments_created
        .checked_add(child_count as u32)
        .ok_or(SiliciumError::InvalidParams)?;

    require!(projected_total <= job.max_fragments, SiliciumError::TooManyFragments);

    if parent.status == FragmentStatus::Claimed {
        splitter_worker.active_claims = splitter_worker.active_claims.saturating_sub(1);
    }

    parent.status = FragmentStatus::SplitPending;
    parent.split_manifest_hash = manifest_hash;
    parent.splitter_worker = ctx.accounts.splitter.key();
    parent.children_count = child_count;

    let proposal = &mut ctx.accounts.split_proposal;
    proposal.job = job.key();
    proposal.parent_fragment = parent.key();
    proposal.splitter_worker = ctx.accounts.splitter.key();
    proposal.manifest_hash = manifest_hash;
    proposal.child_count = child_count;
    proposal.approved = false;
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

    Ok(())
}
