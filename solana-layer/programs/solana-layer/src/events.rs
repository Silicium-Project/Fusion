use anchor_lang::prelude::*;

#[event]
pub struct JobCreated {
    pub job: Pubkey,
    pub client: Pubkey,
    pub mint: Pubkey,
    pub escrow: Pubkey,
    pub job_id: u64,
    pub expected_fragments: u32,
    pub reward_per_fragment: u64,
    pub verifier_reward_per_vote: u64,
    pub verifier_reward_budget: u64,
    pub deposited_amount: u64,
    pub deadline_unix: i64,
    pub fragment_quorum: u16,
}

#[event]
pub struct WorkerRegistered {
    pub worker: Pubkey,
    pub worker_account: Pubkey,
    pub roles: u8,
    pub status: u8,
}

#[event]
pub struct WorkerStaked {
    pub worker: Pubkey,
    pub worker_account: Pubkey,
    pub mint: Pubkey,
    pub stake_vault: Pubkey,
    pub amount: u64,
    pub total_stake: u64,
}

#[event]
pub struct TreasuryInitialized {
    pub mint: Pubkey,
    pub treasury_state: Pubkey,
    pub treasury_auth: Pubkey,
    pub treasury: Pubkey,
    pub admin: Pubkey,
}

#[event]
pub struct FragmentClaimed {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    // V2: utile pour tracer le compte de paiement du worker.
    pub worker_token_account: Pubkey,
    pub claim_deadline_unix: i64,
    pub round: u16,
}

#[event]
pub struct FragmentReclaimed {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub previous_worker: Pubkey,
    pub caller: Pubkey,
    pub round: u16,
}

#[event]
pub struct FragmentSubmitted {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub worker_token_account: Pubkey,
    pub round: u16,
    pub result_hash: [u8; 32],
    pub proof_ref: [u8; 32],
    pub is_resubmission: bool,
}

#[event]
pub struct FragmentVerified {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub verifier: Pubkey,
    pub worker_reward: u64,
    pub verifier_reward_per_vote: u64,
    pub eligible_verifier_rewards: u16,
    pub yes_votes: u16,
    pub round: u16,
    pub verified_fragments: u32,
    pub expected_fragments: u32,
}

#[event]
pub struct FragmentRejected {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub fragment_index: u32,
    pub worker: Pubkey,
    pub verifier: Pubkey,
    pub verifier_reward_per_vote: u64,
    pub eligible_verifier_rewards: u16,
    pub no_votes: u16,
    pub round: u16,
}

#[event]
pub struct VerifierRewardClaimed {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub verifier: Pubkey,
    pub vote: Pubkey,
    pub round: u16,
    pub amount: u64,
    pub claimed_rewards: u16,
    pub eligible_rewards: u16,
}

#[event]
pub struct JobFinalized {
    pub job: Pubkey,
    pub client: Pubkey,
    pub result: Pubkey,
    pub final_hash: [u8; 32],
    pub refunded_amount: u64,
    pub verified_fragments: u32,
    pub expected_fragments: u32,
}

#[event]
pub struct JobCancelled {
    pub job: Pubkey,
    pub client: Pubkey,
    pub refunded_amount: u64,
}

#[event]
pub struct VoteSlashed {
    pub job: Pubkey,
    pub fragment: Pubkey,
    pub vote: Pubkey,
    pub verifier: Pubkey,
    pub slash_amount: u64,
    pub round: u16,
    pub fragment_status: u8,
    pub treasury: Pubkey,
}

#[event]
pub struct WorkerReputationUpdated {
    pub worker: Pubkey,
    pub old_reputation: i64,
    pub new_reputation: i64,
    pub delta: i64,
    pub reason: u8,
    pub status: u8,
}

// V2: event détaillé pour auditer la mémoire bayésienne court terme / long terme.
#[event]
pub struct BayesianReputationUpdated {
    pub worker: Pubkey,
    pub reason: u8,
    pub reputation: i64,
    pub reliability_score: u32,
    pub compute_alpha_long: u64,
    pub compute_beta_long: u64,
    pub compute_alpha_short: u64,
    pub compute_beta_short: u64,
    pub verify_alpha_long: u64,
    pub verify_beta_long: u64,
    pub verify_alpha_short: u64,
    pub verify_beta_short: u64,
    pub fraud_strikes: u16,
    pub error_strikes: u16,
}

// V2: events de sous-fragmentation.
#[event]
pub struct FragmentSplitProposed {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub parent_fragment_index: u32,
    pub proposal: Pubkey,
    pub splitter_worker: Pubkey,
    pub manifest_hash: [u8; 32],
    pub child_count: u16,
    pub depth: u8,
    pub complexity_score: u32,
}

#[event]
pub struct FragmentSplitApproved {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub parent_fragment_index: u32,
    pub proposal: Pubkey,
    pub authority: Pubkey,
    pub child_count: u16,
    pub new_expected_fragments: u32,
    pub total_fragments_created: u32,
}

#[event]
pub struct FragmentSplitRejected {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub parent_fragment_index: u32,
    pub proposal: Pubkey,
    pub authority: Pubkey,
}

#[event]
pub struct SubFragmentCreated {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub child_fragment: Pubkey,
    pub child_fragment_index: u32,
    pub depth: u8,
    pub required_reputation: i64,
    pub required_stake: u64,
    pub complexity_score: u32,
    pub input_hash: [u8; 32],
    pub created_children: u16,
    pub child_count: u16,
}

#[event]
pub struct FragmentSplitCompleted {
    pub job: Pubkey,
    pub parent_fragment: Pubkey,
    pub parent_fragment_index: u32,
    pub proposal: Pubkey,
    pub child_count: u16,
}

#[event]
pub struct StakingPoolInitialized {
    pub pool: Pubkey,
    pub mint: Pubkey,
    pub authority: Pubkey,
    pub stake_vault: Pubkey,
    pub reward_vault: Pubkey,
}

#[event]
pub struct NetworkStakeDeposited {
    pub pool: Pubkey,
    pub staker: Pubkey,
    pub owner: Pubkey,
    pub amount: u64,
    pub total_staked: u64,
    pub user_stake_amount: u64,
}

#[event]
pub struct StakingRewardsFunded {
    pub pool: Pubkey,
    pub funder: Pubkey,
    pub amount: u64,
    pub total_staked: u64,
    pub acc_reward_per_share: u128,
}

#[event]
pub struct StakingRewardClaimed {
    pub pool: Pubkey,
    pub staker: Pubkey,
    pub owner: Pubkey,
    pub amount: u64,
}

#[event]
pub struct NetworkUnstakeRequested {
    pub pool: Pubkey,
    pub staker: Pubkey,
    pub owner: Pubkey,
    pub amount: u64,
    pub remaining_stake: u64,
    pub available_at: i64,
}

#[event]
pub struct NetworkUnstakeWithdrawn {
    pub pool: Pubkey,
    pub staker: Pubkey,
    pub owner: Pubkey,
    pub amount: u64,
}
