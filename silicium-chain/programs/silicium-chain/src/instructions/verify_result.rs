use anchor_lang::prelude::*;
use solana_program::hash::hashv;

use crate::{errors::SiliciumError, events::*, state::*};

"""Verifiers vote to approve/reject."""

#[derive(AnchorSerialize, AnchorDeserialize)]
pub struct VerifyResultArgs {
    pub approved: bool,
}

#[derive(Accounts)]
pub struct VerifyResult<'info> {
    #[account(mut)]
    pub verifier: Signer<'info>,

    #[account(mut)]
    pub assignment: Account<'info, Assignment>,
}

fn update_accumulator(prev: [u8; 32], verifier: Pubkey) -> [u8; 32] {
    let v = verifier.to_bytes();
    hashv(&[&prev, &v]).to_bytes()
}

pub fn handler(ctx: Context<VerifyResult>, args: VerifyResultArgs) -> Result<()> {
    let a = &mut ctx.accounts.assignment;
    require!(matches!(a.status, AssignmentStatus::Submitted), SiliciumError::BadTaskStatus);

    let new_acc = update_accumulator(a.verifier_acc_hash, ctx.accounts.verifier.key());
    require!(new_acc != a.verifier_acc_hash, SiliciumError::AlreadyVerified);
    a.verifier_acc_hash = new_acc;

    if args.approved {
        a.approvals = a.approvals.saturating_add(1);
    } else {
        a.rejections = a.rejections.saturating_add(1);
    }

    emit!(ResultVerified {
        assignment: a.key(),
        verifier: ctx.accounts.verifier.key(),
        approved: args.approved,
        approvals: a.approvals,
        rejections: a.rejections,
    });

    Ok(())
}
