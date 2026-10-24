use anchor_lang::prelude::*;

#[account]
pub struct Treasury {
    pub mint: Pubkey,
    pub authority: Pubkey,
    pub admin: Pubkey,
    pub bump: u8,
    pub treasury_token_account: Pubkey,
}

impl Treasury {
    pub const SPACE: usize =
        8   // discr
        + 32 // mint
        + 32 // authority
        + 32 // admin
        + 1 // bump
        + 32; // treasury_token_account
}
