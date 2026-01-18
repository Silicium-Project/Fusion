use anchor_lang::prelude::*;

""" entry point of the Solana program."""

pub mod constants;
pub mod errors;
pub mod events;
pub mod instructions;
pub mod state;

use instructions::*;

declare_id!("SiLiCiUm1111111111111111111111111111111111");

#[program]
pub mod silicium {
    use super::*;

    pub fn init_config(ctx: Context<InitConfig>, args: InitConfigArgs) -> Result<()> {
        instructions::init_config::handler(ctx, args)
    }

    pub fn register_worker(ctx: Context<RegisterWorker>, args: RegisterWorkerArgs) -> Result<()> {
        instructions::register_worker::handler(ctx, args)
    }

    pub fn submit_task(ctx: Context<SubmitTask>, args: SubmitTaskArgs) -> Result<()> {
        instructions::submit_task::handler(ctx, args)
    }

    pub fn fund_task(ctx: Context<FundTask>, args: FundTaskArgs) -> Result<()> {
        instructions::fund_task::handler(ctx, args)
    }

    pub fn assign_work(ctx: Context<AssignWork>, args: AssignWorkArgs) -> Result<()> {
        instructions::assign_work::handler(ctx, args)
    }

    pub fn submit_result(ctx: Context<SubmitResult>, args: SubmitResultArgs) -> Result<()> {
        instructions::submit_result::handler(ctx, args)
    }

    pub fn verify_result(ctx: Context<VerifyResult>, args: VerifyResultArgs) -> Result<()> {
        instructions::verify_result::handler(ctx, args)
    }

    pub fn finalize_task(ctx: Context<FinalizeTask>) -> Result<()> {
        instructions::finalize_task::handler(ctx)
    }

    pub fn claim_reward(ctx: Context<ClaimReward>) -> Result<()> {
        instructions::claim_reward::handler(ctx)
    }

    pub fn slash_worker(ctx: Context<SlashWorker>, args: SlashWorkerArgs) -> Result<()> {
        instructions::slash_worker::handler(ctx, args)
    }
}
