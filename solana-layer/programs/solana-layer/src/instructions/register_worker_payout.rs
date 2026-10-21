use anchor_lang::{
    prelude::*,
    solana_program::{
        ed25519_program,
        sysvar::instructions::{load_current_index_checked, load_instruction_at_checked},
    },
};

use crate::{error::SiliciumError, state::worker_payout::WorkerPayout};

#[derive(Accounts)]
pub struct RegisterWorkerPayout<'info> {
    /// The account wallet receiving future SIL rewards and paying for the PDA.
    #[account(mut)]
    pub payout_wallet: Signer<'info>,

    /// CHECK: worker identity is authenticated by the preceding Ed25519 proof.
    pub worker: UncheckedAccount<'info>,

    /// CHECK: must be the canonical Worker PDA for `worker`.
    #[account(seeds = [b"worker", worker.key().as_ref()], bump)]
    pub worker_account: UncheckedAccount<'info>,

    #[account(
        init_if_needed,
        payer = payout_wallet,
        space = WorkerPayout::SPACE,
        seeds = [b"worker_payout", worker_account.key().as_ref()],
        bump
    )]
    pub worker_payout: Account<'info, WorkerPayout>,

    /// CHECK: when changing an existing destination, its current owner must sign.
    pub previous_payout_wallet: UncheckedAccount<'info>,

    /// CHECK: validated against the Ed25519 precompile instruction immediately before this one.
    #[account(address = anchor_lang::solana_program::sysvar::instructions::ID)]
    pub instructions: UncheckedAccount<'info>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<RegisterWorkerPayout>,
    pairing_code: String,
    node_id: String,
    peer_id: String,
) -> Result<()> {
    let worker = ctx.accounts.worker.key();
    let payout_wallet = ctx.accounts.payout_wallet.key();
    if payout_wallet != worker {
        require!(
            pairing_code.len() == 64 && pairing_code.bytes().all(|byte| byte.is_ascii_hexdigit()),
            SiliciumError::InvalidParams
        );
        require!(
            !node_id.is_empty() && node_id.len() <= 64 && node_id.bytes().all(is_node_id_byte),
            SiliciumError::InvalidParams
        );
        require!(
            !peer_id.is_empty() && peer_id.len() <= 128,
            SiliciumError::InvalidParams
        );
        let message = format!(
            "silicium-device-payout-v1\n{pairing_code}\n{node_id}\n{peer_id}\n{worker}\n{payout_wallet}"
        );
        verify_worker_proof(
            &ctx.accounts.instructions.to_account_info(),
            &worker,
            message.as_bytes(),
        )?;
    }

    let payout = &mut ctx.accounts.worker_payout;
    if payout.worker == Pubkey::default() {
        payout.worker = worker;
        payout.payout_wallet = payout_wallet;
        payout.bump = ctx.bumps.worker_payout;
        return Ok(());
    }

    require_keys_eq!(payout.worker, worker, SiliciumError::InvalidParams);
    if payout.payout_wallet != payout_wallet && payout.payout_wallet != worker {
        require_keys_eq!(
            ctx.accounts.previous_payout_wallet.key(),
            payout.payout_wallet,
            SiliciumError::NotAuthorized
        );
        require!(
            ctx.accounts.previous_payout_wallet.is_signer,
            SiliciumError::NotAuthorized
        );
    }
    payout.payout_wallet = payout_wallet;
    Ok(())
}

fn is_node_id_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.')
}

fn verify_worker_proof(
    instructions_sysvar: &AccountInfo,
    worker: &Pubkey,
    expected_message: &[u8],
) -> Result<()> {
    let current_index = load_current_index_checked(instructions_sysvar)
        .map_err(|_| error!(SiliciumError::NotAuthorized))? as usize;
    require!(current_index > 0, SiliciumError::NotAuthorized);
    let proof = load_instruction_at_checked(current_index - 1, instructions_sysvar)
        .map_err(|_| error!(SiliciumError::NotAuthorized))?;
    require_keys_eq!(proof.program_id, ed25519_program::ID, SiliciumError::NotAuthorized);

    let data = proof.data;
    require!(data.len() >= 112 && data[0] == 1 && data[1] == 0, SiliciumError::NotAuthorized);
    let read_u16 = |offset: usize| -> Result<usize> {
        let bytes = data
            .get(offset..offset + 2)
            .ok_or_else(|| error!(SiliciumError::NotAuthorized))?;
        Ok(u16::from_le_bytes([bytes[0], bytes[1]]) as usize)
    };
    let signature_offset = read_u16(2)?;
    let signature_instruction = read_u16(4)?;
    let public_key_offset = read_u16(6)?;
    let public_key_instruction = read_u16(8)?;
    let message_offset = read_u16(10)?;
    let message_size = read_u16(12)?;
    let message_instruction = read_u16(14)?;
    require!(
        signature_instruction == u16::MAX as usize
            && public_key_instruction == u16::MAX as usize
            && message_instruction == u16::MAX as usize,
        SiliciumError::NotAuthorized
    );
    let signature_end = signature_offset
        .checked_add(64)
        .ok_or(SiliciumError::InvalidParams)?;
    let public_key_end = public_key_offset
        .checked_add(32)
        .ok_or(SiliciumError::InvalidParams)?;
    let message_end = message_offset
        .checked_add(message_size)
        .ok_or(SiliciumError::InvalidParams)?;
    require!(
        signature_offset >= 16
            && public_key_offset >= 16
            && message_offset >= 16
            && signature_end <= data.len()
            && public_key_end <= data.len()
            && message_end <= data.len(),
        SiliciumError::NotAuthorized
    );
    let worker_bytes = worker.to_bytes();
    require!(
        data.get(public_key_offset..public_key_end) == Some(&worker_bytes[..]),
        SiliciumError::NotAuthorized
    );
    require!(
        data.get(message_offset..message_end) == Some(expected_message),
        SiliciumError::NotAuthorized
    );
    Ok(())
}
