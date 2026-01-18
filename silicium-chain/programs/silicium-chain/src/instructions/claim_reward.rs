use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{constants::*, errors::SiliciumError, events::*, state::*};

"""The worker retrieves their payment from the vault (escrow → worker ATA)."""

#[derive(Accounts)]
pub struct ClaimReward<'info> {
    pub config: Account<'info, Config>,

    #[account(mut)]
    pub claimant: Signer<'info>,

    #[account(mut)]
    pub worker: Account<'info, Worker>,

    #[account(mut)]
    pub assignment: Account<'info, Assignment>,

    #[account(
        seeds = [SEED_VAULT_AUTH, assignment.task.as_ref()],
        bump
    )]
    /// CHECK: PDA authority for vault_ata
    pub vault_authority: UncheckedAccount<'info>,

    #[account(mut)]
    pub vault_ata: Account<'info, TokenAccount>,

    #[account(mut)]
    pub claimant_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ClaimReward>) -> Result<()> {
    let a = &mut ctx.accounts.assignment;
    require!(matches!(a.status, AssignmentStatus::Finalized), SiliciumError::BadTaskStatus);

    let w = &ctx.accounts.worker;
    require!(w.owner == ctx.accounts.claimant.key(), SiliciumError::Unauthorized);
    require!(w.key() == a.worker, SiliciumError::Unauthorized);

    require!(!a.worker_claimed, SiliciumError::NothingToClaim);
    require!(a.worker_reward > 0, SiliciumError::NothingToClaim);

    let task_key = a.task;
    let bump = ctx.bumps.vault_authority;

    let signer_seeds: &[&[&[u8]]] = &[&[
        SEED_VAULT_AUTH,
        task_key.as_ref(),
        &[bump],
    ]];

    let cpi_accounts = Transfer {
        from: ctx.accounts.vault_ata.to_account_info(),
        to: ctx.accounts.claimant_ata.to_account_info(),
        authority: ctx.accounts.vault_authority.to_account_info(),
    };
    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        cpi_accounts,
        signer_seeds,
    );

    token::transfer(cpi_ctx, a.worker_reward)?;

    a.worker_claimed = true;

    emit!(RewardClaimed {
        claimant: ctx.accounts.claimant.key(),
        amount: a.worker_reward,
    });

    Ok(())
}
