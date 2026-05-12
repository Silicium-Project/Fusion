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

    #[msg("Fragment is already claimed")]
    FragmentAlreadyClaimed,

    #[msg("Fragment claim is still active")]
    ClaimStillActive,

    #[msg("Fragment is not claimed")]
    FragmentNotClaimed,

    #[msg("Fragment claim has expired")]
    ClaimExpired,

    #[msg("Worker reputation is too low")]
    ReputationTooLow,

    #[msg("Job deposit is too small")]
    DepositTooSmall,

    #[msg("Too many fragments for one job")]
    TooManyFragments,

    #[msg("Invalid job deadline")]
    InvalidDeadline,

    #[msg("Job has expired")]
    JobExpired,

    #[msg("Worker has too many active claims")]
    TooManyActiveClaims,

    #[msg("Client cannot verify their own job")]
    ClientCannotVerifyOwnJob,

    #[msg("No stakers in the staking pool")]
    NoStakers,

    #[msg("No staking rewards to claim")]
    NoStakingRewards,

    #[msg("Insufficient staked amount")]
    InsufficientStakedAmount,

    #[msg("Unstake cooldown is still active")]
    UnstakeCooldownActive,

    #[msg("Nothing to withdraw")]
    NothingToWithdraw,

    // V2: erreurs dédiées au split et à la sélection réputation/stake.
    #[msg("Worker stake is too low for this fragment")]
    StakeTooLow,

    #[msg("This fragment is not a leaf fragment")]
    NotLeafFragment,

    #[msg("Parent fragment must be a leaf before split")]
    ParentFragmentNotLeaf,

    #[msg("This fragment has already been split")]
    FragmentAlreadySplit,

    #[msg("Split is not allowed for this fragment")]
    SplitNotAllowed,

    #[msg("Split depth limit exceeded")]
    SplitDepthExceeded,

    #[msg("Split child limit exceeded")]
    SplitChildLimitExceeded,

    #[msg("Fragment complexity is too low to justify a split")]
    SplitComplexityTooLow,

    #[msg("Invalid split manifest hash")]
    InvalidSplitManifest,

    #[msg("Split proposal already exists or is already resolved")]
    SplitAlreadyResolved,

    #[msg("Split proposal is not approved")]
    SplitNotApproved,

    #[msg("Split authority is invalid")]
    InvalidSplitAuthority,

    #[msg("Invalid child fragment index")]
    InvalidChildFragmentIndex,

    #[msg("Parent fragment is not approved for child creation")]
    ParentNotSplitApproved,

    #[msg("Split children are not fully created yet")]
    SplitChildrenIncomplete,
}
