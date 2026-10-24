use anchor_lang::prelude::*;

use crate::{
    constants::DEFAULT_MAX_CHILDREN_PER_FRAGMENT,
    error::SiliciumError,
    events::{FragmentSplitCompleted, SubFragmentCreated},
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
        split_proposal::SplitProposal,
    },
};

#[derive(Accounts)]
#[instruction(child_fragment_index: u32)]
pub struct CreateSubFragment<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    #[account(
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
        mut,
        seeds = [
            b"split_proposal",
            parent_fragment.key().as_ref(),
            &parent_fragment.round.to_le_bytes()
        ],
        bump = split_proposal.bump,
        constraint = split_proposal.job == job.key() @ SiliciumError::InvalidParams,
        constraint = split_proposal.parent_fragment == parent_fragment.key() @ SiliciumError::InvalidParams,
        constraint = split_proposal.approved @ SiliciumError::SplitNotApproved,
        constraint = !split_proposal.rejected @ SiliciumError::SplitAlreadyResolved
    )]
    pub split_proposal: Box<Account<'info, SplitProposal>>,

    #[account(
        init,
        payer = payer,
        space = Fragment::SPACE,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &child_fragment_index.to_le_bytes()
        ],
        bump
    )]
    pub child_fragment: Box<Account<'info, Fragment>>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<CreateSubFragment>,
    child_fragment_index: u32,
    required_compute_reputation: i64,
    required_stake: u64,
    complexity_score: u32,
    input_hash: [u8; 32],
) -> Result<()> {
    let parent = &mut ctx.accounts.parent_fragment;
    let proposal = &mut ctx.accounts.split_proposal;
    let child = &mut ctx.accounts.child_fragment;

    require!(
        child_fragment_index < ctx.accounts.job.max_fragments,
        SiliciumError::InvalidChildFragmentIndex
    );
    require!(
        is_child_index(&ctx.accounts.job, parent.fragment_index, child_fragment_index),
        SiliciumError::InvalidChildFragmentIndex
    );
    require!(parent.status == FragmentStatus::SplitApproved, SiliciumError::ParentNotSplitApproved);
    require!(proposal.created_children < proposal.child_count, SiliciumError::SplitChildLimitExceeded);
    require!(required_compute_reputation >= 0, SiliciumError::InvalidParams);
    require!(input_hash != [0u8; 32], SiliciumError::InvalidParams);

    child.job = ctx.accounts.job.key();
    child.fragment_index = child_fragment_index;
    child.assigned_worker = Pubkey::default();
    child.worker = Pubkey::default();
    child.worker_token_account = Pubkey::default();
    child.result_hash = [0u8; 32];
    child.proof_ref = input_hash;
    child.status = FragmentStatus::Available;
    child.yes_votes = 0;
    child.no_votes = 0;
    child.required_quorum = ctx.accounts.job.fragment_quorum;
    child.claim_deadline_unix = 0;
    child.voting_deadline_unix = 0;
    child.round = 0;

    child.parent_fragment = parent.key();
    child.depth = parent.depth.saturating_add(1);
    child.children_count = 0;
    child.max_children = DEFAULT_MAX_CHILDREN_PER_FRAGMENT;
    child.split_manifest_hash = [0u8; 32];
    child.splitter_worker = Pubkey::default();
    child.is_leaf = true;
    child.required_compute_reputation = required_compute_reputation;
    child.required_stake = required_stake;
    child.complexity_score = complexity_score;
    child.bump = ctx.bumps.child_fragment;

    proposal.created_children = proposal.created_children.saturating_add(1);

    emit!(SubFragmentCreated {
        job: ctx.accounts.job.key(),
        parent_fragment: parent.key(),
        child_fragment: child.key(),
        child_fragment_index,
        depth: child.depth,
        required_compute_reputation,
        required_stake,
        complexity_score,
        input_hash,
        created_children: proposal.created_children,
        child_count: proposal.child_count,
    });

    if proposal.created_children == proposal.child_count {
        parent.status = FragmentStatus::SplitParent;

        emit!(FragmentSplitCompleted {
            job: ctx.accounts.job.key(),
            parent_fragment: parent.key(),
            parent_fragment_index: parent.fragment_index,
            proposal: proposal.key(),
            child_count: proposal.child_count,
        });
    }

    Ok(())
}

/// Maps a binary split tree into a disjoint, pre-reserved index range for
/// each initial root. Root indices stay stable as the leaf count changes.
fn is_child_index(job: &Job, parent_index: u32, child_index: u32) -> bool {
    let roots = job.initial_fragments();
    if roots == 0 || parent_index >= job.max_fragments {
        return false;
    }
    let per_root = job.max_fragments.saturating_sub(roots) / roots;
    if per_root < 2 {
        return false;
    }
    let (root, local) = if parent_index < roots {
        (parent_index, 0)
    } else {
        let offset = parent_index - roots;
        let root = offset / per_root;
        if root >= roots {
            return false;
        }
        (root, offset % per_root + 1)
    };
    let first_local = local.saturating_mul(2).saturating_add(1);
    let second_local = first_local.saturating_add(1);
    if second_local > per_root {
        return false;
    }
    let first = roots + root * per_root + first_local - 1;
    let second = roots + root * per_root + second_local - 1;
    child_index == first || child_index == second
}
