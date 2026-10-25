use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq)]
pub enum FragmentStatus {
    Available,
    Claimed,
    Submitted,
    Verified,
    Rejected,
    SplitPending,
    SplitApproved,
    SplitParent,
}

#[account]
pub struct Fragment {
    pub job: Pubkey,
    pub fragment_index: u32,

    pub assigned_worker: Pubkey,
    pub worker: Pubkey,
    pub worker_token_account: Pubkey,

    pub result_hash: [u8; 32],
    pub proof_ref: [u8; 32],

    pub status: FragmentStatus,

    pub yes_votes: u16,
    pub no_votes: u16,
    pub required_quorum: u16,

    pub claim_deadline_unix: i64,
    pub voting_deadline_unix: i64,

    pub round: u16,

    // V2: arbre de sous-fragments.
    pub parent_fragment: Pubkey,
    pub depth: u8,
    pub children_count: u16,
    pub max_children: u16,
    pub split_manifest_hash: [u8; 32],
    pub splitter_worker: Pubkey,
    pub is_leaf: bool,

    // V2: sélection darwinienne.
    pub required_compute_reputation: i64,
    pub required_stake: u64,
    pub complexity_score: u32,

    pub bump: u8,
}

impl Fragment {
    pub const SPACE: usize = 8   // discriminator
        + 32 // job
        + 4  // fragment_index
        + 32 // assigned_worker
        + 32 // worker
        + 32 // worker_token_account
        + 32 // result_hash
        + 32 // proof_ref
        + 1  // status
        + 2  // yes_votes
        + 2  // no_votes
        + 2  // required_quorum
        + 8  // claim_deadline_unix
        + 8  // voting_deadline_unix
        + 2  // round
        + 32 // parent_fragment
        + 1  // depth
        + 2  // children_count
        + 2  // max_children
        + 32 // split_manifest_hash
        + 32 // splitter_worker
        + 1  // is_leaf
        + 8  // required_compute_reputation
        + 8  // required_stake
        + 4  // complexity_score
        + 1; // bump
}
