use anchor_lang::prelude::*;
use crate::instructions::finalize_job::URI_MAX_LEN;

#[account]
pub struct JobResult {
    pub job: Pubkey,
    pub final_hash: [u8; 32],
    pub uri_len: u16,
    pub uri_bytes: [u8; URI_MAX_LEN],
    pub bump: u8,
}

impl JobResult {
    pub const SPACE: usize =
        8   // discr
        + 32 // job
        + 32 // final_hash
        + 2  // uri_len
        + URI_MAX_LEN
        + 1; // bump
}
