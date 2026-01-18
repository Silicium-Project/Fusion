use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::{constants::*, errors::SiliciumError, events::*, state::*};

"""Put the budget in escrow (user = vault ATA of the PDA vault_authority)."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct FundTaskArgs {
    pub amount: u64,
}

#[derive(Accounts)]
pub struct FundTask<'info> {
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub authority: Signer<'info>,

    #[account(mut, has_one = authority)]
    pub task: Account<'info, Task>,

    pub mint: Account<'info, Mint>,

    #[account(mut)]
    pub user_ata: Account<'info, TokenAccount>,

    #[account(
        seeds = [SEED_VAULT_AUTH, task.key().as_ref()],
        bump
    )]
    /// CHECK: PDA authority for vault_ata
    pub vault_authority: UncheckedAccount<'info>,

    #[account(mut)]
    pub vault_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<FundTask>, args: FundTaskArgs) -> Result<()> {
    require!(ctx.accounts.mint.key() == ctx.accounts.config.mint, SiliciumError::Unauthorized);

    let task = &mut ctx.accounts.task;
    require!(
        matches!(task.status, TaskStatus::Created | TaskStatus::Funded),
        SiliciumError::BadTaskStatus
    );

    // transfer user -> vault
    let cpi_accounts = Transfer {
        from: ctx.accounts.user_ata.to_account_info(),
        to: ctx.accounts.vault_ata.to_account_info(),
        authority: ctx.accounts.authority.to_account_info(),
    };
    let cpi_ctx = CpiContext::new(ctx.accounts.token_program.to_account_info(), cpi_accounts);
    token::transfer(cpi_ctx, args.amount)?;

    task.total_budget = task.total_budget.checked_add(args.amount).ok_or(SiliciumError::MathOverflow)?;
    task.remaining_budget = task.remaining_budget.checked_add(args.amount).ok_or(SiliciumError::MathOverflow)?;
    task.status = TaskStatus::Funded;

    emit!(TaskFunded {
        task: task.key(),
        amount: args.amount,
        total_budget: task.total_budget,
    });

    Ok(())
}
