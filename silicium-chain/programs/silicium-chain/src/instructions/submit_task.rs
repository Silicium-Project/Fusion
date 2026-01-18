use anchor_lang::prelude::*;
use crate::{constants::*, events::*, state::*};

"""The user creates the task (hash metadata + nb subtasks)."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct SubmitTaskArgs {
    pub task_id: u64,
    pub metadata_hash: [u8; 32],
    pub nb_subtasks: u32,
}

#[derive(Accounts)]
#[instruction(args: SubmitTaskArgs)]
pub struct SubmitTask<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,

    #[account(
        init,
        payer = authority,
        space = Task::SIZE,
        seeds = [SEED_TASK, authority.key().as_ref(), &args.task_id.to_le_bytes()],
        bump
    )]
    pub task: Account<'info, Task>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<SubmitTask>, args: SubmitTaskArgs) -> Result<()> {
    let now = Clock::get()?.unix_timestamp;

    let task = &mut ctx.accounts.task;
    task.authority = ctx.accounts.authority.key();
    task.task_id = args.task_id;
    task.status = TaskStatus::Created;

    task.metadata_hash = args.metadata_hash;
    task.nb_subtasks = args.nb_subtasks;

    task.total_budget = 0;
    task.remaining_budget = 0;

    task.created_at = now;
    task.bump = ctx.bumps.task;

    emit!(TaskSubmitted {
        task: task.key(),
        authority: task.authority,
        task_id: task.task_id,
        nb_subtasks: task.nb_subtasks,
        metadata_hash: task.metadata_hash,
    });

    Ok(())
}
