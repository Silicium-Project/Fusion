use anchor_lang::prelude::*;

use crate::state::worker::{Worker, WorkerStatus};

#[derive(Accounts)]
pub struct RegisterWorker<'info> {
    #[account(mut)]
    pub worker: Signer<'info>,

    #[account(
        init,
        payer = worker,
        space = Worker::SPACE,
        seeds = [b"worker", worker.key().as_ref()],
        bump
    )]
    pub worker_account: Account<'info, Worker>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<RegisterWorker>) -> Result<()> {
    let w = &mut ctx.accounts.worker_account;
    w.owner = ctx.accounts.worker.key();
    w.stake_amount = 0;
    w.reputation = 0;
    w.total_submitted = 0;
    w.total_verified = 0;
    w.total_rejected = 0;
    w.status = WorkerStatus::Active;
    w.bump = ctx.bumps.worker_account;
    Ok(())
}
