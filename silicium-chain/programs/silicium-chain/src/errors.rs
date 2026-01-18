use anchor_lang::prelude::*;

"""Errors when a business rule fails."""

#[error_code]
pub enum SiliciumError {
    #[msg("Unauthorized")]
    Unauthorized,

    #[msg("Bad task status for this operation")]
    BadTaskStatus,

    #[msg("Insufficient task budget")]
    InsufficientBudget,

    #[msg("Invalid verifier count")]
    InvalidVerifierCount,

    #[msg("Already verified by this verifier (anti-double-vote guard)")]
    AlreadyVerified,

    #[msg("Assignment has no submitted result")]
    NoResultSubmitted,

    #[msg("Assignment not ready to finalize")]
    AssignmentNotFinalizable,

    #[msg("Nothing to claim")]
    NothingToClaim,

    #[msg("Result deadline exceeded")]
    DeadlineExceeded,

    #[msg("Math overflow")]
    MathOverflow,
}
