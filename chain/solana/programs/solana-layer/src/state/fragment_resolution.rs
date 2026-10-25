use anchor_lang::prelude::*;

#[account]
pub struct FragmentResolution {
    pub fragment: Pubkey,
    pub round: u16,
    pub resolved: bool,
    pub winning_choice: bool,
    pub eligible_rewards: u16,
    pub claimed_rewards: u16,
    pub bump: u8,
}

impl FragmentResolution {
    pub const SPACE: usize = 8  // discriminator
        + 32                    // fragment
        + 2                     // round
        + 1                     // resolved
        + 1                     // winning_choice
        + 2                     // eligible_rewards
        + 2                     // claimed_rewards
        + 1; // bump
}
