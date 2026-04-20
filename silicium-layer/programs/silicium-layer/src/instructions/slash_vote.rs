use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};

use crate::{
    error::SiliciumError,
    state::{
        fragment::{Fragment, FragmentStatus},
        fragment_vote::FragmentVote,
        job::Job,
        treasury::Treasury,
        worker::Worker,
    },
};

pub const SLASH_BPS: u64 = 1000; // 10%
pub const BPS_DENOM: u64 = 10_000;

#[derive(Accounts)]
pub struct SlashVote<'info> {
    /// Anyone can call (permissionless)
    #[account(mut)]
    pub slasher: Signer<'info>,

    pub job: Box<Account<'info, Job>>,

    #[account(
        seeds = [
            b"fragment",
            job.key().as_ref(),
            &fragment.fragment_index.to_le_bytes()
        ],
        bump = fragment.bump
    )]
    pub fragment: Box<Account<'info, Fragment>>,

    #[account(
        mut,
        seeds = [
            b"fragment_vote",
            fragment.key().as_ref(),
            vote.verifier.as_ref(),
            &vote.round.to_le_bytes()
        ],
        bump = vote.bump,
        constraint = vote.fragment == fragment.key() @ SiliciumError::InvalidParams
    )]

    pub vote: Box<Account<'info, FragmentVote>>,

    #[account(
        mut,
        seeds = [b"worker", vote.verifier.as_ref()],
        bump = verifier_worker.bump,
        constraint = verifier_worker.owner == vote.verifier @ SiliciumError::NotAuthorized
    )]
    pub verifier_worker: Box<Account<'info, Worker>>,

    /// Treasury config PDA
    #[account(
        seeds = [b"treasury", job.mint.as_ref()],
        bump = treasury_state.bump,
        constraint = treasury_state.mint == job.mint @ SiliciumError::WrongStakeMint
    )]
    pub treasury_state: Box<Account<'info, Treasury>>,

    /// CHECK: PDA authority of stake vault
    #[account(
        seeds = [b"stake_auth", verifier_worker.key().as_ref()],
        bump
    )]
    pub stake_auth: UncheckedAccount<'info>,

    #[account(
        mut,
        seeds = [b"stake_vault", vote.verifier.as_ref()],
        bump,
        constraint = stake_vault.owner == stake_auth.key() @ SiliciumError::NotAuthorized,
        constraint = stake_vault.mint == job.mint @ SiliciumError::WrongStakeMint
    )]
    pub stake_vault: Box<Account<'info, TokenAccount>>,

    /// CHECK: treasury authority PDA (must match treasury_state.authority)
    #[account(
        seeds = [b"treasury_auth", job.mint.as_ref()],
        bump,
        constraint = treasury_auth.key() == treasury_state.authority @ SiliciumError::NotAuthorized
    )]
    pub treasury_auth: UncheckedAccount<'info>,

    #[account(
        mut,
        constraint = treasury.mint == job.mint @ SiliciumError::WrongStakeMint,
        constraint = treasury.owner == treasury_auth.key() @ SiliciumError::NotAuthorized,
        constraint = treasury.key() == treasury_state.treasury_token_account @ SiliciumError::WrongTreasuryAccount
    )]
    pub treasury: Box<Account<'info, TokenAccount>>,

    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<SlashVote>) -> Result<()> {
    let fragment = &ctx.accounts.fragment;
    let vote = &mut ctx.accounts.vote;
    let verifier_worker = &mut ctx.accounts.verifier_worker;

    // Must be resolved
    require!(
        fragment.status != FragmentStatus::Submitted,
        SiliciumError::FragmentNotResolved
    );

    // Prevent double slashing
    require!(!vote.slashed, SiliciumError::VoteAlreadySlashed);

    // Determine if vote is wrong side
    let wrong = match fragment.status {
        FragmentStatus::Verified => vote.choice == false,
        FragmentStatus::Rejected => vote.choice == true,
        FragmentStatus::Submitted => false,
    };
    require!(wrong, SiliciumError::NothingToSlash);

    let stake_amount = verifier_worker.stake_amount;
    require!(stake_amount > 0, SiliciumError::NothingToSlash);

    // slash_amount = max(1, stake * 10%)
    let mut slash_amount = stake_amount
        .saturating_mul(SLASH_BPS)
        .checked_div(BPS_DENOM)
        .unwrap_or(0);

    if slash_amount == 0 {
        slash_amount = 1;
    }

    // Clamp to vault balance
    let vault_amt = ctx.accounts.stake_vault.amount;
    if slash_amount > vault_amt {
        slash_amount = vault_amt;
    }
    require!(slash_amount > 0, SiliciumError::NothingToSlash);

    // signer seeds for stake_auth
    let verifier_worker_key = verifier_worker.key();
    let bump = ctx.bumps.stake_auth;

    let seeds: &[&[u8]] = &[b"stake_auth", verifier_worker_key.as_ref(), &[bump]];
    let signer_seeds: &[&[&[u8]]] = &[seeds];

    // Transfer stake_vault -> treasury
    let cpi_ctx = CpiContext::new_with_signer(
        ctx.accounts.token_program.to_account_info(),
        Transfer {
            from: ctx.accounts.stake_vault.to_account_info(),
            to: ctx.accounts.treasury.to_account_info(),
            authority: ctx.accounts.stake_auth.to_account_info(),
        },
        signer_seeds,
    );
    token::transfer(cpi_ctx, slash_amount)?;

    verifier_worker.stake_amount = verifier_worker.stake_amount.saturating_sub(slash_amount);
    vote.slashed = true;

    Ok(())
}
