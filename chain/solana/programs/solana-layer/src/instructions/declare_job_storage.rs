use anchor_lang::prelude::*;

use crate::{
    error::SiliciumError,
    events::JobStorageDeclared,
    state::{
        job::{Job, JobStatus},
        job_storage::JobStorage,
    },
};

#[derive(Accounts)]
pub struct DeclareJobStorage<'info> {
    #[account(mut)]
    pub client: Signer<'info>,

    #[account(
        constraint = job.client == client.key() @ SiliciumError::NotAuthorized,
        constraint = job.status == JobStatus::Open @ SiliciumError::JobFinalized
    )]
    pub job: Box<Account<'info, Job>>,

    #[account(
        init,
        payer = client,
        space = JobStorage::SPACE,
        seeds = [b"job_storage", job.key().as_ref()],
        bump
    )]
    pub job_storage: Account<'info, JobStorage>,

    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<DeclareJobStorage>,
    manifest_hash: [u8; 32],
    input_root_hash: [u8; 32],
    storage_ref_hash: [u8; 32],
    encryption_ref_hash: [u8; 32],
) -> Result<()> {
    require!(
        manifest_hash != [0u8; 32],
        SiliciumError::InvalidStorageHash
    );
    require!(
        input_root_hash != [0u8; 32],
        SiliciumError::InvalidStorageHash
    );
    require!(
        storage_ref_hash != [0u8; 32],
        SiliciumError::InvalidStorageHash
    );

    let now = Clock::get()?.unix_timestamp;
    let job_key = ctx.accounts.job.key();

    let storage = &mut ctx.accounts.job_storage;
    storage.job = job_key;
    storage.manifest_hash = manifest_hash;
    storage.input_root_hash = input_root_hash;
    storage.storage_ref_hash = storage_ref_hash;
    storage.encryption_ref_hash = encryption_ref_hash;
    storage.declared_by = ctx.accounts.client.key();
    storage.created_at_unix = now;
    storage.bump = ctx.bumps.job_storage;

    emit!(JobStorageDeclared {
        job: job_key,
        job_storage: storage.key(),
        client: ctx.accounts.client.key(),
        manifest_hash,
        input_root_hash,
        storage_ref_hash,
        encryption_ref_hash,
        created_at_unix: now,
    });

    Ok(())
}
