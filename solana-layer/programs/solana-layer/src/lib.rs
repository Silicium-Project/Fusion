use anchor_lang::prelude::*;

pub mod instructions;
pub mod state;
pub mod error;

pub use instructions::*;

declare_id!("2ni1Y5VUFZDoQVhsQEf6LyM8kKXEic3CSpckrcLJzaD4");

#[program]
pub mod solana_layer {
    use super::*;

    pub fn create_job(
        ctx: Context<CreateJob>,
        job_id: u64,
        expected_fragments: u32,
        reward_per_fragment: u64,
        deadline_unix: i64,
        fragment_quorum: u16,
    ) -> Result<()> {
        crate::instructions::create_job::handler(
            ctx,
            job_id,
            expected_fragments,
            reward_per_fragment,
            deadline_unix,
            fragment_quorum,
        )
    }

    pub fn submit_fragment_result(
        ctx: Context<SubmitFragmentResult>,
        fragment_index: u32,
        result_hash: [u8; 32],
        proof_ref: [u8; 32],
    ) -> Result<()> {
        crate::instructions::submit_fragment_result::handler(
            ctx,
            fragment_index,
            result_hash,
            proof_ref,
        )
    }

    pub fn register_worker(ctx: Context<RegisterWorker>) -> Result<()> {
        crate::instructions::register_worker::handler(ctx)
    }

    pub fn stake_worker(ctx: Context<StakeWorker>, amount: u64) -> Result<()> {
        crate::instructions::stake_worker::handler(ctx, amount)
    }

    pub fn vote_fragment(ctx: Context<VoteFragment>, choice: bool) -> Result<()> {
        crate::instructions::vote_fragment::handler(ctx, choice)
    }

    pub fn finalize_job(
        ctx: Context<FinalizeJob>,
        final_hash: [u8; 32],
        output_uri: Vec<u8>,
    ) -> Result<()> {
        crate::instructions::finalize_job::handler(ctx, final_hash, output_uri)
    }

    pub fn cancel_job(ctx: Context<CancelJob>) -> Result<()> {
        crate::instructions::cancel_job::handler(ctx)
    }

    pub fn init_treasury(ctx: Context<InitTreasury>) -> Result<()> {
        crate::instructions::init_treasury::handler(ctx)
    }

    pub fn slash_vote(ctx: Context<SlashVote>) -> Result<()> {
        crate::instructions::slash_vote::handler(ctx)
    }

    pub fn resubmit_fragment_result(
        ctx: Context<ResubmitFragmentResult>,
        fragment_index: u32,
        result_hash: [u8; 32],
        proof_ref: [u8; 32],
    ) -> Result<()> {
        crate::instructions::resubmit_fragment_result::handler(
            ctx,
            fragment_index,
            result_hash,
            proof_ref,
        )
    }
}
