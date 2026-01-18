use anchor_lang::prelude::*;
use crate::{errors::SiliciumError, events::*, state::*};

"""admin/scheduler penalizes a worker (reputation) + marks assignment slashed."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct SlashWorkerArgs {
    pub penalty_reputation: i64,
    pub reason_code: u16,
}

#[derive(Accounts)]
pub struct SlashWorker<'info> {
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub authority: Signer<'info>, // admin or scheduler

    #[account(mut)]
    pub worker: Account<'info, Worker>,

    #[account(mut)]
    pub assignment: Account<'info, Assignment>,
}

pub fn handler(ctx: Context<SlashWorker>, args: SlashWorkerArgs) -> Result<()> {
    let cfg = &ctx.accounts.config;
    let auth = ctx.accounts.authority.key();
    require!(auth == cfg.admin || auth == cfg.scheduler, SiliciumError::Unauthorized);

    let a = &mut ctx.accounts.assignment;
    require!(a.worker == ctx.accounts.worker.key(), SiliciumError::Unauthorized);

    a.status = AssignmentStatus::Slashed;

    let w = &mut ctx.accounts.worker;
    w.reputation = w.reputation.saturating_sub(args.penalty_reputation.abs());

    emit!(WorkerSlashed {
        worker: w.key(),
        penalty_reputation: args.penalty_reputation.abs(),
        reason_code: args.reason_code,
    });

    Ok(())
}
