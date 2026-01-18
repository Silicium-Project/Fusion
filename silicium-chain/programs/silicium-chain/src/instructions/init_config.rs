use anchor_lang::prelude::*;
use crate::{constants::*, errors::SiliciumError, events::*, state::*};

"""Create the Config (PDA) account only once."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct InitConfigArgs {
    pub admin: Pubkey,
    pub scheduler: Pubkey,
    pub mint: Pubkey,
    pub fee_bps: u16,
}

#[derive(Accounts)]
pub struct InitConfig<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,

    #[account(
        init,
        payer = payer,
        space = Config::SIZE,
        seeds = [SEED_CONFIG],
        bump
    )]
    pub config: Account<'info, Config>,

    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<InitConfig>, args: InitConfigArgs) -> Result<()> {
    require!(args.fee_bps <= 10_000, SiliciumError::MathOverflow);

    let cfg = &mut ctx.accounts.config;
    cfg.admin = args.admin;
    cfg.scheduler = args.scheduler;
    cfg.mint = args.mint;
    cfg.fee_bps = args.fee_bps;
    cfg.bump = ctx.bumps.config;

    emit!(ConfigInitialized {
        admin: cfg.admin,
        scheduler: cfg.scheduler,
        mint: cfg.mint,
        fee_bps: cfg.fee_bps,
    });

    Ok(())
}
