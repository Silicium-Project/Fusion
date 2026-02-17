use anchor_lang::prelude::*;

pub mod instructions;
pub mod state;
pub mod error;

#[allow(unused_imports)]
use crate::instructions::create_job::__client_accounts_create_job;
#[allow(unused_imports)]
use crate::instructions::submit_fragment_result::__client_accounts_submit_fragment_result;
#[allow(unused_imports)]
use crate::instructions::finalize_job::__client_accounts_finalize_job;
#[allow(unused_imports)]
use crate::instructions::cancel_job::__client_accounts_cancel_job;
#[allow(unused_imports)]
use crate::instructions::register_worker::__client_accounts_register_worker;
#[allow(unused_imports)]
use crate::instructions::vote_fragment::__client_accounts_vote_fragment;
#[allow(unused_imports)]
use crate::instructions::stake_worker::__client_accounts_stake_worker;
#[allow(unused_imports)]
use crate::instructions::slash_vote::__client_accounts_slash_vote;
#[allow(unused_imports)]
use crate::instructions::init_treasury::__client_accounts_init_treasury;
#[allow(unused_imports)]
use crate::instructions::resubmit_fragment_result::__client_accounts_resubmit_fragment_result;

use crate::instructions::create_job::CreateJob;
use crate::instructions::submit_fragment_result::SubmitFragmentResult;
use crate::instructions::finalize_job::FinalizeJob;
use crate::instructions::cancel_job::CancelJob;
use crate::instructions::register_worker::RegisterWorker;
use crate::instructions::vote_fragment::VoteFragment;
use crate::instructions::stake_worker::StakeWorker;
use crate::instructions::slash_vote::SlashVote;
use crate::instructions::init_treasury::InitTreasury;
use crate::instructions::resubmit_fragment_result::ResubmitFragmentResult;

declare_id!("4LHNxzAoaumTaJC5zC8C4tRvR71Gwi48YjLraeuVMLsU");

#[program]
pub mod silicium_chain {
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
