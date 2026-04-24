use anchor_lang::prelude::*;

#[error_code]
pub enum SiliciumError {
    #[msg("Invalid parameters.")]
    InvalidParams,

    #[msg("Invalid amount.")]
    InvalidAmount,

    #[msg("Not authorized.")]
    NotAuthorized,

    #[msg("Job is not open.")]
    JobFinalized,

    #[msg("Fragment is in a bad state.")]
    BadFragmentState,

    #[msg("Missing compute role.")]
    MissingComputeRole,

    #[msg("Missing verify role.")]
    MissingVerifyRole,

    #[msg("Self vote is forbidden.")]
    SelfVoteForbidden,

    #[msg("Voting is closed.")]
    VotingClosed,

    #[msg("Insufficient escrow balance.")]
    InsufficientEscrow,

    #[msg("Not ready to finalize.")]
    NotReadyToFinalize,

    #[msg("URI too long.")]
    UriTooLong,

    #[msg("Job is not cancellable.")]
    JobNotCancellable,

    #[msg("Fragment not resolved yet.")]
    FragmentNotResolved,

    #[msg("Vote already slashed.")]
    VoteAlreadySlashed,

    #[msg("Nothing to slash.")]
    NothingToSlash,

    #[msg("Wrong stake mint.")]
    WrongStakeMint,

    #[msg("Wrong stake vault.")]
    WrongStakeVault,

    #[msg("Wrong treasury account.")]
    WrongTreasuryAccount,

    #[msg("Reward already claimed.")]
    RewardAlreadyClaimed,

    #[msg("Vote is not eligible for reward.")]
    VoteNotEligibleForReward,

    #[msg("Insufficient verifier reward budget.")]
    InsufficientVerifierBudget,

    #[msg("Outstanding verifier claims must be settled first.")]
    OutstandingVerifierClaims,
}