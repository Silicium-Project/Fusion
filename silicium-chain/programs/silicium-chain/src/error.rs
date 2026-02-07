use anchor_lang::prelude::*;

#[error_code]
pub enum SiliciumError {
    #[msg("Invalid parameters")]
    InvalidParams,
    #[msg("Not authorized")]
    NotAuthorized,
    #[msg("Job already finalized")]
    JobFinalized,
    #[msg("Fragment state invalid")]
    BadFragmentState,
    #[msg("Escrow has insufficient funds")]
    InsufficientEscrow,
    #[msg("Job not ready to finalize")]
    NotReadyToFinalize,
    #[msg("URI too long")]
    UriTooLong,
    #[msg("Job not cancellable yet")]
    JobNotCancellable,
}
