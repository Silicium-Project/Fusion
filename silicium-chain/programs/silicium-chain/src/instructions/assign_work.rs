use anchor_lang::prelude::*;
use crate::{constants::*, errors::SiliciumError, events::*, state::*};

"""The off-chain scheduler creates an assignment and reserves the budget."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct AssignWorkArgs {
    pub assignment_id: u64,
    pub worker: Pubkey,
    pub subtask_index: u32,
    pub reward: u64,
    pub required_verifiers: u8,
    pub result_deadline: i64,
}

#[derive(Accounts)]
#[instruction(args: AssignWorkArgs)]
pub struct AssignWork<'info> {
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub scheduler: Signer<'info>,

    #[account(mut)]
    pub task: Account<'info, Task>,

    #[account(
        init,
        payer = scheduler,
        space = Assignment::SIZE,
        seeds = [SEED_ASSIGNMENT, task.key().as_ref(), &args.assignment_id.to_le_bytes()],
        bump
    )]
    pub assignment: Account<'info, Assignment>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<AssignWork>, args: AssignWorkArgs) -> Result<()> {
    require!(ctx.accounts.scheduler.key() == ctx.accounts.config.scheduler, SiliciumError::Unauthorized);
    require!(args.required_verifiers > 0, SiliciumError::InvalidVerifierCount);

    let task = &mut ctx.accounts.task;
    require!(matches!(task.status, TaskStatus::Funded | TaskStatus::Assigned), SiliciumError::BadTaskStatus);
    require!(task.remaining_budget >= args.reward, SiliciumError::InsufficientBudget);

    task.remaining_budget = task.remaining_budget.checked_sub(args.reward).ok_or(SiliciumError::MathOverflow)?;
    task.status = TaskStatus::Assigned;

    let a = &mut ctx.accounts.assignment;
    a.task = task.key();
    a.worker = args.worker;
    a.assignment_id = args.assignment_id;
    a.subtask_index = args.subtask_index;

    a.reward = args.reward;
    a.required_verifiers = args.required_verifiers;
    a.approvals = 0;
    a.rejections = 0;
    a.verifier_acc_hash = [0u8; 32];

    a.result_hash = [0u8; 32];
    a.result_deadline = args.result_deadline;

    a.status = AssignmentStatus::Assigned;

    a.worker_reward = 0;
    a.verifier_pool = 0;
    a.fee_amount = 0;

    a.worker_claimed = false;
    a.bump = ctx.bumps.assignment;

    emit!(WorkAssigned {
        task: task.key(),
        assignment: a.key(),
        assignment_id: a.assignment_id,
        worker: a.worker,
        subtask_index: a.subtask_index,
        reward: a.reward,
        required_verifiers: a.required_verifiers,
    });

    Ok(())
}
