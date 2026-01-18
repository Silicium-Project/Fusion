use anchor_lang::prelude::*;

"""Global protocol parameters (admin, scheduler, mint token, fee)."""

#[account]
pub struct Config {
    pub admin: Pubkey,
    pub scheduler: Pubkey, // backend authority allowed to assign work
    pub mint: Pubkey,      // SPL mint used for escrow and rewards
    pub fee_bps: u16,      // fee in basis points (100 = 1%)
    pub bump: u8,
}

impl Config {
    pub const SIZE: usize = 8 + 32 + 32 + 32 + 2 + 1;
}
