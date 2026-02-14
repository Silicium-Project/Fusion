use anchor_lang::prelude::*;
use anchor_spl::token::{Mint, Token, TokenAccount};

use crate::state::treasury::Treasury;

#[derive(Accounts)]
pub struct InitTreasury<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    pub mint: Account<'info, Mint>,

    /// Treasury config PDA (stores mint/authority/admin)
    #[account(
        init,
        payer = payer,
        space = Treasury::SPACE,
        seeds = [b"treasury", mint.key().as_ref()],
        bump
    )]
    pub treasury_state: Account<'info, Treasury>,

    /// CHECK: PDA authority that owns the treasury token account
    #[account(
        seeds = [b"treasury_auth", mint.key().as_ref()],
        bump
    )]
    pub treasury_auth: UncheckedAccount<'info>,

    /// Treasury token account (holds slashed tokens)
    #[account(
        init,
        payer = payer,
        token::mint = mint,
        token::authority = treasury_auth
    )]
    pub treasury: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<InitTreasury>) -> Result<()> {
    let t = &mut ctx.accounts.treasury_state;

    t.mint = ctx.accounts.mint.key();
    t.authority = ctx.accounts.treasury_auth.key();
    t.admin = ctx.accounts.payer.key();
    t.bump = ctx.bumps.treasury_state;

    Ok(())
}
