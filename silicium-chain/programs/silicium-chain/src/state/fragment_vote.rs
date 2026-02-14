use anchor_lang::prelude::*;

#[account]
pub struct FragmentVote {
    pub fragment: Pubkey,
    pub verifier: Pubkey,
    pub choice: bool,

    pub slashed: bool,
    pub bump: u8,
}

impl FragmentVote {
    pub const SPACE: usize = 8 + 32 + 32 + 1 + 1 + 1;
}
