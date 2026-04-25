use anchor_lang::prelude::*;

use crate::{
    error::SiliciumError,
    events::FragmentReclaimed,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::{Job, JobStatus},
    },
};

#[derive(Accounts)]
#[instruction(fragment_index: u32)]
pub struct ReclaimFragment<'info> {
    #[account(mut)]
    pub caller: Signer<'info>,

    #[account(
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    #[account(
        mut,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment_index.to_le_bytes()
        ],
        bump = fragment.bump,
        constraint = fragment.job == job.key() @ SiliciumError::InvalidParams,
        constraint = fragment.fragment_index == fragment_index @ SiliciumError::InvalidParams
    )]
    pub fragment: Account<'info, Fragment>,
}

pub fn handler(ctx: Context<ReclaimFragment>, fragment_index: u32) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;

    let job_key = ctx.accounts.job.key();
    let fragment_key = ctx.accounts.fragment.key();
    let caller_key = ctx.accounts.caller.key();

    let f = &mut ctx.accounts.fragment;

    require!(f.status == FragmentStatus::Claimed, SiliciumError::BadFragmentState);
    require!(now >= f.claim_deadline_unix, SiliciumError::ClaimStillActive);

    let previous_worker = f.assigned_worker;
    let round = f.round;

    f.assigned_worker = Pubkey::default();
    f.claim_deadline_unix = 0;
    f.status = FragmentStatus::Available;

    emit!(FragmentReclaimed {
        job: job_key,
        fragment: fragment_key,
        fragment_index,
        previous_worker,
        caller: caller_key,
        round,
    });

    Ok(())
}
