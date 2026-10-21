use anchor_lang::prelude::*;

pub mod constants;
pub mod error;
pub mod events;
pub mod instructions;
pub mod state;

pub use instructions::*;

declare_id!("A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2");

#[program]
pub mod solana_layer {
    use super::*;

    pub fn create_job(
        ctx: Context<CreateJob>,
        job_id: u64,
        expected_fragments: u32,
        reward_per_fragment: u64,
        verifier_reward_per_vote: u64,
        verifier_reward_budget: u64,
        deadline_unix: i64,
        fragment_quorum: u16,
    ) -> Result<()> {
        crate::instructions::create_job::handler(
            ctx,
            job_id,
            expected_fragments,
            reward_per_fragment,
            verifier_reward_per_vote,
            verifier_reward_budget,
            deadline_unix,
            fragment_quorum,
        )
    }

    pub fn declare_job_storage(
        ctx: Context<DeclareJobStorage>,
        manifest_hash: [u8; 32],
        input_root_hash: [u8; 32],
        storage_ref_hash: [u8; 32],
        encryption_ref_hash: [u8; 32],
    ) -> Result<()> {
        crate::instructions::declare_job_storage::handler(
            ctx,
            manifest_hash,
            input_root_hash,
            storage_ref_hash,
            encryption_ref_hash,
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

    pub fn register_worker_payout(
        ctx: Context<RegisterWorkerPayout>,
        pairing_code: String,
        node_id: String,
        peer_id: String,
    ) -> Result<()> {
        crate::instructions::register_worker_payout::handler(ctx, pairing_code, node_id, peer_id)
    }

    pub fn stake_worker(ctx: Context<StakeWorker>, amount: u64) -> Result<()> {
        crate::instructions::stake_worker::handler(ctx, amount)
    }

    pub fn vote_fragment(ctx: Context<VoteFragment>, choice: bool) -> Result<()> {
        crate::instructions::vote_fragment::handler(ctx, choice)
    }

    pub fn claim_verifier_reward(ctx: Context<ClaimVerifierReward>) -> Result<()> {
        crate::instructions::claim_verifier_reward::handler(ctx)
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

    pub fn claim_fragment(ctx: Context<ClaimFragment>, fragment_index: u32) -> Result<()> {
        crate::instructions::claim_fragment::handler(ctx, fragment_index)
    }

    pub fn reclaim_fragment(ctx: Context<ReclaimFragment>, fragment_index: u32) -> Result<()> {
        crate::instructions::reclaim_fragment::handler(ctx, fragment_index)
    }

    pub fn init_staking_pool(ctx: Context<InitStakingPool>) -> Result<()> {
        crate::instructions::init_staking_pool::handler(ctx)
    }

    pub fn stake_network(ctx: Context<StakeNetwork>, amount: u64) -> Result<()> {
        crate::instructions::stake_network::handler(ctx, amount)
    }

    pub fn fund_staking_rewards(ctx: Context<FundStakingRewards>, amount: u64) -> Result<()> {
        crate::instructions::fund_staking_rewards::handler(ctx, amount)
    }

    pub fn claim_staking_reward(ctx: Context<ClaimStakingReward>) -> Result<()> {
        crate::instructions::claim_staking_reward::handler(ctx)
    }

    pub fn request_unstake(ctx: Context<RequestUnstake>, amount: u64) -> Result<()> {
        crate::instructions::request_unstake::handler(ctx, amount)
    }

    pub fn withdraw_unstaked(ctx: Context<WithdrawUnstaked>) -> Result<()> {
        crate::instructions::withdraw_unstaked::handler(ctx)
    }

    // V2: sous-fragmentation contrôlée.
    pub fn propose_fragment_split(
        ctx: Context<ProposeFragmentSplit>,
        manifest_hash: [u8; 32],
        child_count: u16,
    ) -> Result<()> {
        crate::instructions::propose_fragment_split::handler(ctx, manifest_hash, child_count)
    }

    pub fn approve_fragment_split(ctx: Context<ApproveFragmentSplit>, approve: bool) -> Result<()> {
        crate::instructions::approve_fragment_split::handler(ctx, approve)
    }

    pub fn create_sub_fragment(
        ctx: Context<CreateSubFragment>,
        child_fragment_index: u32,
        required_compute_reputation: i64,
        required_stake: u64,
        complexity_score: u32,
        input_hash: [u8; 32],
    ) -> Result<()> {
        crate::instructions::create_sub_fragment::handler(
            ctx,
            child_fragment_index,
            required_compute_reputation,
            required_stake,
            complexity_score,
            input_hash,
        )
    }
}
