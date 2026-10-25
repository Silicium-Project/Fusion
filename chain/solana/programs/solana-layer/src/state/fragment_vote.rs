use anchor_lang::prelude::*;

#[account]
pub struct FragmentVote {
    pub fragment: Pubkey,
    pub verifier: Pubkey,
    pub choice: bool,
    pub round: u16,
    pub slashed: bool,
    pub reward_claimed: bool,
    pub bump: u8,
}

impl FragmentVote {
    pub const SPACE: usize = 8  // discriminator
        + 32                    // fragment
        + 32                    // verifier
        + 1                     // choice
        + 2                     // round
        + 1                     // slashed
        + 1                     // reward_claimed
        + 1; // bump
}
