use anchor_lang::prelude::*;

/// Storage metadata for a Silicium job.
///
/// The Solana layer stores only hashes and references. The real task inputs,
/// manifests, outputs, and proof files remain off-chain in the P2P/storage layer.
#[account]
pub struct JobStorage {
    /// Parent job this storage metadata belongs to.
    pub job: Pubkey,

    /// Canonical SHA-256 hash of the complete off-chain job manifest.
    pub manifest_hash: [u8; 32],

    /// Root hash/checksum for all task inputs declared by the manifest.
    pub input_root_hash: [u8; 32],

    /// Hash of the storage routing reference or storage manifest.
    ///
    /// This should generally be the hash of a small off-chain storage manifest
    /// containing P2P CIDs/URIs and content checksums, not just the hash of a URL.
    pub storage_ref_hash: [u8; 32],

    /// Optional hash of encryption/key-distribution metadata.
    ///
    /// A zero hash means the job does not declare encryption metadata on-chain.
    pub encryption_ref_hash: [u8; 32],

    /// Wallet that declared the storage metadata.
    pub declared_by: Pubkey,

    /// On-chain timestamp of the declaration.
    pub created_at_unix: i64,

    pub bump: u8,
}

impl JobStorage {
    pub const SPACE: usize = 8  // discriminator
        + 32                    // job
        + 32                    // manifest_hash
        + 32                    // input_root_hash
        + 32                    // storage_ref_hash
        + 32                    // encryption_ref_hash
        + 32                    // declared_by
        + 8                     // created_at_unix
        + 1;                    // bump
}
