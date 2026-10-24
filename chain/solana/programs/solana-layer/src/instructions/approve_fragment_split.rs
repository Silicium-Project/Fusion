use anchor_lang::prelude::*;

use crate::{
    error::SiliciumError,
    events::{FragmentSplitApproved, FragmentSplitRejected},
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        split_proposal::SplitProposal,
    },
};

#[derive(Accounts)]
pub struct ApproveFragmentSplit<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,

    #[account(
        mut,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized,
        constraint = job.split_authority == authority.key() @ SiliciumError::InvalidSplitAuthority
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
        mut,
        seeds = [
            b"split_proposal",
            parent_fragment.key().as_ref(),
            &parent_fragment.round.to_le_bytes()
        ],
        bump = split_proposal.bump,
        constraint = split_proposal.job == job.key() @ SiliciumError::InvalidParams,
        constraint = split_proposal.parent_fragment == parent_fragment.key() @ SiliciumError::InvalidParams
    )]
    pub split_proposal: Account<'info, SplitProposal>,
}

pub fn handler(ctx: Context<ApproveFragmentSplit>, approve: bool) -> Result<()> {
    let job = &mut ctx.accounts.job;
    let parent = &mut ctx.accounts.parent_fragment;
    let proposal = &mut ctx.accounts.split_proposal;

    // V2.6 auto-approves an eligible split in the splitter's transaction.
    // Keep this legacy client call idempotent for older SDK flows.
    if proposal.approved
        && matches!(parent.status, FragmentStatus::SplitApproved | FragmentStatus::SplitParent)
    {
        return Ok(());
    }

    require!(parent.status == FragmentStatus::SplitPending, SiliciumError::BadFragmentState);
    require!(!proposal.approved, SiliciumError::SplitAlreadyResolved);
    require!(!proposal.rejected, SiliciumError::SplitAlreadyResolved);
    require!(proposal.child_count >= 2, SiliciumError::SplitChildLimitExceeded);

    if !approve {
        proposal.rejected = true;
        parent.status = FragmentStatus::Available;
        parent.split_manifest_hash = [0u8; 32];
        parent.splitter_worker = Pubkey::default();
        parent.children_count = 0;

        emit!(FragmentSplitRejected {
            job: job.key(),
            parent_fragment: parent.key(),
            parent_fragment_index: parent.fragment_index,
            proposal: proposal.key(),
            authority: ctx.accounts.authority.key(),
        });

        return Ok(());
    }

    let new_expected = job
        .expected_fragments
        .saturating_sub(1)
        .checked_add(proposal.child_count as u32)
        .ok_or(SiliciumError::InvalidParams)?;

    require!(new_expected <= job.max_fragments, SiliciumError::TooManyFragments);

    proposal.approved = true;
    parent.status = FragmentStatus::SplitApproved;
    parent.is_leaf = false;

    // Le parent est remplacé par ses enfants dans le nombre de leaf fragments attendus.
    job.expected_fragments = new_expected;
    job.total_fragments_created = job
        .total_fragments_created
        .checked_add(proposal.child_count as u32)
        .ok_or(SiliciumError::InvalidParams)?;

    emit!(FragmentSplitApproved {
        job: job.key(),
        parent_fragment: parent.key(),
        parent_fragment_index: parent.fragment_index,
        proposal: proposal.key(),
        authority: ctx.accounts.authority.key(),
        child_count: proposal.child_count,
        new_expected_fragments: job.expected_fragments,
        total_fragments_created: job.total_fragments_created,
    });

    Ok(())
}
