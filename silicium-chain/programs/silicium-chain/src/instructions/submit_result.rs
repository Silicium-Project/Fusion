use anchor_lang::prelude::*;
use crate::{errors::SiliciumError, events::*, state::*};


"""the worker submits the hash of the result"""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct SubmitResultArgs {
    pub result_hash: [u8; 32],
}

#[derive(Accounts)]
pub struct SubmitResult<'info> {
    #[account(mut)]
    pub worker_owner: Signer<'info>,

    #[account(mut)]
    pub worker: Account<'info, Worker>,

    #[account(mut)]
    pub assignment: Account<'info, Assignment>,
}

pub fn handler(ctx: Context<SubmitResult>, args: SubmitResultArgs) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;

    let worker = &ctx.accounts.worker;
    require!(worker.owner == ctx.accounts.worker_owner.key(), SiliciumError::Unauthorized);

    let a = &mut ctx.accounts.assignment;
    require!(a.worker == worker.key(), SiliciumError::Unauthorized);
    require!(matches!(a.status, AssignmentStatus::Assigned), SiliciumError::BadTaskStatus);

    require!(now <= a.result_deadline, SiliciumError::DeadlineExceeded);

    a.result_hash = args.result_hash;
    a.status = AssignmentStatus::Submitted;

    emit!(ResultSubmitted {
        assignment: a.key(),
        worker: a.worker,
        result_hash: a.result_hash,
    });

    Ok(())
}
