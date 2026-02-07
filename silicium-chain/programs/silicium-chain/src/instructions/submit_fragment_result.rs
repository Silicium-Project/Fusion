use anchor_lang::prelude::*;

use crate::{
    error::SiliciumError,
    state::{
        fragment::{Fragment, FragmentStatus},
        job::Job,
    },
};

#[derive(Accounts)]
#[instruction(fragment_index: u32)]
pub struct SubmitFragmentResult<'info> {
    #[account(mut)]
    pub worker: Signer<'info>,

    #[account(
        constraint = !job.is_finalized @ SiliciumError::JobFinalized
    )]
    pub job: Account<'info, Job>,

    #[account(
        init,
        payer = worker,
        space = Fragment::SPACE,
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment_index.to_le_bytes(),
            worker.key().as_ref()
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
    proof_ref: [u8; 32],
) -> Result<()> {
    require!(
        fragment_index < ctx.accounts.job.expected_fragments,
        SiliciumError::InvalidParams
    );

    let f = &mut ctx.accounts.fragment;
    f.job = ctx.accounts.job.key();
    f.fragment_index = fragment_index;
    f.worker = ctx.accounts.worker.key();
    f.result_hash = result_hash;
    f.proof_ref = proof_ref;
    f.status = FragmentStatus::Submitted;
    f.bump = ctx.bumps.fragment;

    Ok(())
}
