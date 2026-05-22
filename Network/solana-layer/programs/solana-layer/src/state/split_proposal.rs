use anchor_lang::prelude::*;

#[account]
pub struct SplitProposal {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub splitter_worker: Pubkey,
    pub manifest_hash: [u8; 32],
    pub child_count: u16,
    pub approved: bool,
    pub rejected: bool,
    pub created_children: u16,
    pub bump: u8,
}

impl SplitProposal {
    pub const SPACE: usize = 8
        + 32 // job
        + 32 // parent_fragment
        + 32 // splitter_worker
        + 32 // manifest_hash
        + 2  // child_count
        + 1  // approved
        + 1  // rejected
        + 2  // created_children
        + 1; // bump
}
