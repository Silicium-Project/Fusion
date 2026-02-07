use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum FragmentStatus {
    Submitted,
    Verified,
    Rejected,
}

#[account]
pub struct Fragment {
    pub job: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub result_hash: [u8; 32],
    pub proof_ref: [u8; 32],
    pub status: FragmentStatus,
    pub bump: u8,
}

impl Fragment {
    pub const SPACE: usize =
        8   // discr
        + 32 // job
        + 4  // fragment_index
        + 32 // worker
        + 32 // result_hash
        + 32 // proof_ref
        + 1  // status
        + 1; // bump
}
