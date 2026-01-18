use anchor_lang::prelude::*;
use crate::{errors::SiliciumError, events::*, state::*};

"""calculates the decision (approved or not) 
    + split rewards (fee/verifiers/worker) + reputation update."""

#[derive(Accounts)]
pub struct FinalizeTask<'info> {
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub assignment: Account<'info, Assignment>,

    #[account(mut)]
    pub worker: Account<'info, Worker>,
}

pub fn handler(ctx: Context<FinalizeTask>) -> Result<()> {
    let cfg = &ctx.accounts.config;
    let a = &mut ctx.accounts.assignment;

    require!(matches!(a.status, AssignmentStatus::Submitted), SiliciumError::BadTaskStatus);
    require!(a.result_hash != [0u8; 32], SiliciumError::NoResultSubmitted);

    // Approval rule (simple):
    // approvals >= required_verifiers AND approvals > rejections
    let approved = a.approvals >= a.required_verifiers && a.approvals > a.rejections;

    // fee = reward * fee_bps / 10000
    let fee_amount = (a.reward as u128)
        .checked_mul(cfg.fee_bps as u128).ok_or(SiliciumError::MathOverflow)?
        .checked_div(10_000).ok_or(SiliciumError::MathOverflow)? as u64;

    // verifier pool fixed 10% (PFE; can be config later)
    let verifier_pool = (a.reward as u128)
        .checked_mul(1_000u128).ok_or(SiliciumError::MathOverflow)?
        .checked_div(10_000).ok_or(SiliciumError::MathOverflow)? as u64;

    let mut worker_reward = a.reward
        .checked_sub(fee_amount).ok_or(SiliciumError::MathOverflow)?
        .checked_sub(verifier_pool).ok_or(SiliciumError::MathOverflow)?;

    if !approved {
        // if rejected, worker gets 0 (policy can be adapted)
        worker_reward = 0;
    }

    a.fee_amount = fee_amount;
    a.verifier_pool = verifier_pool;
    a.worker_reward = worker_reward;
    a.status = AssignmentStatus::Finalized;

    // Update worker stats/reputation
    let w = &mut ctx.accounts.worker;
    if w.key() == a.worker {
        w.total_jobs = w.total_jobs.saturating_add(1);
        if approved {
            w.success_jobs = w.success_jobs.saturating_add(1);
            w.reputation = w.reputation.saturating_add(1);
        } else {
            w.reputation = w.reputation.saturating_sub(2);
        }
    }

    emit!(AssignmentFinalized {
        assignment: a.key(),
        approved,
        worker_reward: a.worker_reward,
        verifier_pool: a.verifier_pool,
        fee_amount: a.fee_amount,
    });

    Ok(())
}
