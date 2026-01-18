use anchor_lang::prelude::*;
use crate::{constants::*, events::*, state::*};

"""A worker registers (creation of the Worker PDA account)."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct RegisterWorkerArgs {
    pub worker_id: u64,
}

#[derive(Accounts)]
#[instruction(args: RegisterWorkerArgs)]
pub struct RegisterWorker<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    #[account(
        init,
        payer = owner,
        space = Worker::SIZE,
        seeds = [SEED_WORKER, owner.key().as_ref(), &args.worker_id.to_le_bytes()],
        bump
    )]
    pub worker: Account<'info, Worker>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<RegisterWorker>, args: RegisterWorkerArgs) -> Result<()> {
    let w = &mut ctx.accounts.worker;
    w.owner = ctx.accounts.owner.key();
    w.worker_id = args.worker_id;
    w.reputation = 0;
    w.total_jobs = 0;
    w.success_jobs = 0;
    w.bump = ctx.bumps.worker;

    emit!(WorkerRegistered {
        worker: w.key(),
        owner: w.owner,
        worker_id: w.worker_id,
    });

    Ok(())
}
