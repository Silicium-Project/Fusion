use anchor_lang::prelude::*;

use crate::{
    events::WorkerRegistered,
    state::{
        reputation::init_bayesian_reputation,
        worker::{Worker, WorkerStatus, ROLE_AUTO, ROLE_COMPUTE, ROLE_VERIFY},
        worker_payout::WorkerPayout,
    },
};

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

    #[account(
        init_if_needed,
        payer = worker,
        space = WorkerPayout::SPACE,
        seeds = [b"worker_payout", worker_account.key().as_ref()],
        bump
    )]
    pub worker_payout: Account<'info, WorkerPayout>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<RegisterWorker>) -> Result<()> {
    let worker_key = ctx.accounts.worker.key();
    let worker_account_key = ctx.accounts.worker_account.key();

    let w = &mut ctx.accounts.worker_account;

    w.owner = worker_key;

    w.stake_mint = Pubkey::default();
    w.stake_vault = Pubkey::default();
    w.stake_amount = 0;

    w.total_submitted = 0;
    w.total_verified = 0;
    w.total_rejected = 0;

    w.active_claims = 0;
    w.roles = ROLE_COMPUTE | ROLE_VERIFY;
    w.preferred_role = ROLE_AUTO;
    w.status = WorkerStatus::Active;
    w.bump = ctx.bumps.worker_account;

    init_bayesian_reputation(w);

    let payout = &mut ctx.accounts.worker_payout;
    if payout.worker == Pubkey::default() {
        payout.worker = worker_key;
        payout.payout_wallet = worker_key;
        payout.bump = ctx.bumps.worker_payout;
    } else {
        require_keys_eq!(payout.worker, worker_key, crate::error::SiliciumError::InvalidParams);
    }

    emit!(WorkerRegistered {
        worker: worker_key,
        worker_account: worker_account_key,
        roles: w.roles,
        status: w.status as u8,
    });

    Ok(())
}
