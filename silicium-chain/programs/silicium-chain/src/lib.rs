use anchor_lang::prelude::*;

pub mod instructions;
pub mod state;
pub mod error;

// ✅ IMPORTANT : ramener le module généré au root
use crate::instructions::create_job::__client_accounts_create_job;

use instructions::create_job::CreateJob;

declare_id!("9fXMziZ32jdmisi7YgQPG6LWX884AWSs1efpNFrJg6wC");

#[program]
pub mod silicium_chain {
    use super::*;

    pub fn create_job(
        ctx: Context<CreateJob>,
        job_id: u64,
        expected_fragments: u32,
        reward_per_fragment: u64,
        deadline_unix: i64,
    ) -> Result<()> {
        instructions::create_job::handler(
            ctx,
            job_id,
            expected_fragments,
            reward_per_fragment,
            deadline_unix,
        )
    }
}

