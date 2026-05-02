# Technical Documentation — Silicium Solana Layer

Version: 0.2  
Project: **Silicium / EIP**  
Anchor program: `solana-layer`  
Current Program ID used in the latest local tests: `9wuEBw5quCa5nxwAuwbb344Hks4o5TnKC5EyKq7jtgDu`

> Note: if Anchor reports a program ID mismatch, run `anchor keys sync`, then rebuild. The program ID in this document should always be aligned with `declare_id!`, `Anchor.toml`, the generated IDL, and the keypair in `target/deploy`.

---

## 1. Purpose of the Solana Layer

The **Solana Layer** is the on-chain settlement, validation, staking, reputation, and reward layer of the Silicium project.

It does not execute distributed computation directly. Computation is performed off-chain by workers. The Anchor program manages the economic guarantees, job state, fragment state, validation votes, escrowed payments, verifier rewards, passive network staking, cancellation, finalization, reputation updates, and slashing.

The program is responsible for:

- registering workers and verifiers;
- staking SPL tokens before participating as an active worker or verifier;
- creating jobs funded through an escrow token account;
- splitting jobs into fragments;
- allowing workers to claim fragments;
- limiting how many fragments a worker can claim in parallel;
- allowing workers to submit fragment results;
- opening a short voting window after each submission;
- allowing verifiers to vote on submitted results;
- paying workers when a fragment reaches a positive quorum;
- making verifier rewards claimable after a winning vote;
- updating worker/verifier reputation after important actions;
- rejecting and resubmitting fragments;
- reclaiming expired fragment claims;
- finalizing or cancelling jobs;
- slashing incorrect verifier votes;
- allowing passive users to stake on the network and claim staking rewards.

---

## 2. High-Level Architecture

The Solana Layer is built around five main domains:

1. **Jobs** — computation tasks submitted by a client and funded in advance.
2. **Fragments** — smaller units of work derived from a job.
3. **Votes and resolutions** — verifier decisions on submitted fragment results.
4. **Workers and reputation** — active participants who compute or verify.
5. **Passive network staking** — non-worker users who stake tokens to support the network and receive reward distributions.

Main computation flow:

```text
Client
  └── create_job
        └── SPL escrow funded
              └── worker claim_fragment
                    └── worker submit_fragment_result
                          └── voting window opens
                                └── verifiers vote_fragment
                                      ├── YES quorum => fragment verified + worker paid + compute reputation increases
                                      └── NO quorum  => fragment rejected + compute reputation decreases
                                            └── resubmit_fragment_result possible
```

Passive staking flow:

```text
Admin / payer
  └── init_staking_pool

Passive user
  └── stake_network
        └── tokens moved to staking vault

Funder / treasury / protocol
  └── fund_staking_rewards
        └── rewards distributed through acc_reward_per_share

Passive user
  ├── claim_staking_reward
  └── request_unstake
        └── cooldown
              └── withdraw_unstaked
```

Once all fragments are verified and all eligible verifier rewards are claimed, the client can finalize the job.

---

## 3. Actors

### 3.1 Client

The client is the user who creates and funds a job.

The required escrow deposit is:

```text
expected_fragments * reward_per_fragment + verifier_reward_budget
```

The client can:

- create a job;
- cancel a job under the program rules;
- finalize a job once all fragments are verified;
- recover the remaining escrow balance during finalization or cancellation.

Security rule added during this session:

- the client cannot verify their own job through `vote_fragment`.

### 3.2 Worker

A worker is a machine that executes computation fragments off-chain.

A worker must:

- be registered through `register_worker`;
- have the compute role;
- be active;
- have at least the minimum compute stake;
- have at least the minimum compute reputation;
- have fewer than `MAX_ACTIVE_CLAIMS_PER_WORKER` active claims;
- claim a fragment before submitting a result.

### 3.3 Verifier

A verifier checks submitted fragment results and votes on them.

A verifier must:

- be registered through `register_worker`;
- have the verify role;
- be active;
- have at least the minimum verifier stake;
- have at least the minimum verifier reputation;
- not be the worker who submitted the fragment;
- not be the job client.

### 3.4 Slasher

The slasher can be any signer. The slasher calls `slash_vote` when a verifier vote is incorrect relative to the resolved result of the fragment round.

The slasher does not need to be the job client, a worker, or a verifier.

### 3.5 Passive Network Staker

A passive network staker is a user who supports the network economically without computing or verifying fragments.

A passive staker can:

- stake tokens into the global staking pool for a mint;
- accumulate proportional staking rewards;
- claim pending rewards;
- request unstake;
- withdraw after the cooldown.

Passive stakers are separate from active workers. They do not need a `Worker` account.

---

## 4. Constants

The current layer uses the following important constants.

| Constant | Purpose | Current test/default value |
|---|---|---:|
| `MIN_FRAGMENT_QUORUM` | Minimum quorum per fragment | `1` |
| `MAX_FRAGMENT_QUORUM` | Maximum quorum per fragment | `10` |
| `MIN_JOB_DEPOSIT` | Minimum job escrow deposit | `1_000_000` |
| `MAX_FRAGMENTS_PER_JOB` | Maximum fragments in one job | `1_000` |
| `MIN_JOB_TTL_SECS` | Minimum job lifetime | `60` |
| `MAX_JOB_TTL_SECS` | Maximum job lifetime | `7 days` |
| `VOTING_TTL_SECS` | Voting window after submission | `300` |
| `MAX_ACTIVE_CLAIMS_PER_WORKER` | Max parallel claims per worker | `5` |
| `REWARD_SCALE` | Fixed-point scale for staking rewards | `1_000_000_000_000` |
| `MIN_NETWORK_STAKE` | Minimum passive stake amount | `1_000_000` |
| `UNSTAKE_COOLDOWN_SECS` | Passive unstake cooldown | `5` for tests |

Production note: `UNSTAKE_COOLDOWN_SECS` is intentionally short for local tests. For beta/mainnet, a value such as `3 * 24 * 60 * 60` is more realistic.

---

## 5. Main Accounts

### 5.1 `Job`

The `Job` account stores the global state of a computation task.

| Field | Description |
|---|---|
| `job_id` | Logical ID provided by the client |
| `client` | Job creator |
| `mint` | SPL mint used for payments |
| `escrow` | Token account funded by the client |
| `expected_fragments` | Total number of fragments required |
| `verified_fragments` | Number of fragments already verified |
| `reward_per_fragment` | Worker reward per verified fragment |
| `verifier_reward_per_vote` | Reward per winning verifier vote |
| `verifier_reward_budget` | Total budget reserved for verifier rewards |
| `deposited_amount` | Initial amount deposited in escrow |
| `paid_amount` | Total amount already paid |
| `claimable_verifier_rewards_total` | Total verifier rewards that became claimable |
| `claimed_verifier_rewards_total` | Total verifier rewards already claimed |
| `created_at_unix` | Creation timestamp |
| `deadline_unix` | Global job deadline |
| `verified_at_unix` | Timestamp when all fragments became verified |
| `fragment_quorum` | Required quorum per fragment |
| `status` | `Open`, `Finalized`, or `Cancelled` |
| `bump` | Job PDA bump |
| `escrow_auth_bump` | Escrow authority PDA bump |

PDA:

```text
[b"job", client, job_id_le_u64]
```

### 5.2 `Fragment`

The `Fragment` account represents one unit of work belonging to a job.

| Field | Description |
|---|---|
| `job` | Parent job |
| `fragment_index` | Fragment index |
| `assigned_worker` | Worker that claimed the fragment |
| `worker` | Worker that submitted the result |
| `worker_token_account` | Token account paid if the fragment is verified |
| `result_hash` | Submitted result hash |
| `proof_ref` | Reference to an off-chain proof or artifact |
| `status` | `Available`, `Claimed`, `Submitted`, `Verified`, or `Rejected` |
| `yes_votes` | Positive votes in the current round |
| `no_votes` | Negative votes in the current round |
| `required_quorum` | Required vote quorum |
| `claim_deadline_unix` | Expiration timestamp of the worker claim |
| `voting_deadline_unix` | Vote deadline for the submitted result |
| `round` | Current fragment round |
| `bump` | Fragment PDA bump |

PDA:

```text
[b"fragment", job, fragment_index_le_u32]
```

### 5.3 `Worker`

The `Worker` account stores the identity, role, stake, reputation, and active claim state of a worker or verifier.

| Field | Description |
|---|---|
| `owner` | Owner wallet |
| `stake_mint` | SPL mint used for active worker staking |
| `stake_vault` | Token vault holding the active worker stake |
| `stake_amount` | Amount currently staked as an active worker/verifier |
| `reputation` | Reputation score from `0` to `10_000` |
| `total_submitted` | Number of submitted results |
| `total_verified` | Successful verification-related counter |
| `total_rejected` | Rejection/failure-related counter |
| `active_claims` | Number of currently claimed but not yet submitted/reclaimed fragments |
| `roles` | Compute and/or verify role flags |
| `status` | `Active`, `Suspended`, or `Banned` |
| `bump` | Worker PDA bump |

PDA:

```text
[b"worker", worker_pubkey]
```

Role flags:

```text
ROLE_COMPUTE = 1
ROLE_VERIFY  = 2
```

### 5.4 `FragmentVote`

The `FragmentVote` account stores one verifier vote for one fragment and one round.

| Field | Description |
|---|---|
| `fragment` | Fragment voted on |
| `verifier` | Verifier wallet |
| `choice` | `true` for YES, `false` for NO |
| `round` | Fragment round |
| `slashed` | Whether the vote has been slashed |
| `reward_claimed` | Whether the vote reward has been claimed |
| `bump` | Vote PDA bump |

PDA:

```text
[b"fragment_vote", fragment, verifier, round_le_u16]
```

This PDA prevents a verifier from voting more than once per fragment per round.

### 5.5 `FragmentResolution`

The `FragmentResolution` account stores the final result of a voting round.

| Field | Description |
|---|---|
| `fragment` | Fragment resolved |
| `round` | Resolved round |
| `resolved` | Whether the round has been resolved |
| `winning_choice` | Winning side of the round |
| `eligible_rewards` | Number of verifier rewards eligible for the round |
| `claimed_rewards` | Number of verifier rewards already claimed |
| `bump` | Resolution PDA bump |

PDA:

```text
[b"fragment_resolution", fragment, round_le_u16]
```

### 5.6 `JobResult`

The `JobResult` account is created when a job is finalized.

PDA:

```text
[b"result", job]
```

It stores:

- the final result hash;
- the output URI encoded as bytes;
- the real output URI length.

The current maximum output URI length is:

```text
128 bytes
```

### 5.7 `Treasury`

The `Treasury` account stores the treasury configuration used to receive slashed tokens.

Treasury state PDA:

```text
[b"treasury", mint]
```

Treasury authority PDA:

```text
[b"treasury_auth", mint]
```

### 5.8 `StakingPool`

The `StakingPool` account stores the global passive staking state for one SPL mint.

| Field | Description |
|---|---|
| `mint` | SPL mint accepted by the pool |
| `authority` | PDA authority for staking vaults |
| `stake_vault` | Vault holding passive user stakes |
| `reward_vault` | Vault holding passive staking rewards |
| `total_staked` | Total passive stake in the pool |
| `acc_reward_per_share` | Fixed-point accumulated reward per share |
| `bump` | Pool PDA bump |
| `authority_bump` | Pool authority PDA bump |

PDA:

```text
[b"staking_pool", mint]
```

Pool authority PDA:

```text
[b"staking_pool_auth", mint]
```

### 5.9 `NetworkStaker`

The `NetworkStaker` account stores the passive staking state of one user for one mint.

| Field | Description |
|---|---|
| `owner` | Staker wallet |
| `mint` | SPL mint being staked |
| `stake_amount` | Active passive stake amount |
| `reward_debt` | Accounting value for proportional reward distribution |
| `pending_rewards` | Rewards already accrued but not claimed |
| `unstake_requested_amount` | Amount waiting for cooldown before withdrawal |
| `unstake_available_at` | Timestamp when pending unstake can be withdrawn |
| `bump` | Staker PDA bump |

PDA:

```text
[b"network_staker", owner, mint]
```

---

## 6. PDA Reference

| Object | Seeds |
|---|---|
| Job | `[b"job", client, job_id_le_u64]` |
| Escrow authority | `[b"escrow_auth", job]` |
| Fragment | `[b"fragment", job, fragment_index_le_u32]` |
| Worker | `[b"worker", worker]` |
| Stake authority | `[b"stake_auth", worker_account]` |
| Stake vault | `[b"stake_vault", worker]` |
| Fragment vote | `[b"fragment_vote", fragment, verifier, round_le_u16]` |
| Fragment resolution | `[b"fragment_resolution", fragment, round_le_u16]` |
| Job result | `[b"result", job]` |
| Treasury state | `[b"treasury", mint]` |
| Treasury authority | `[b"treasury_auth", mint]` |
| Staking pool | `[b"staking_pool", mint]` |
| Staking pool authority | `[b"staking_pool_auth", mint]` |
| Network staker | `[b"network_staker", owner, mint]` |

---

## 7. Reputation System

A functional reputation system was added during this session.

The model is intentionally simple and deterministic so that it remains easy to test on-chain.

### 7.1 Reputation Bounds

```text
REPUTATION_MIN   = 0
REPUTATION_MAX   = 10_000
REPUTATION_START = 5_000
```

Workers start with a neutral reputation of `5_000`.

### 7.2 Role Thresholds

| Threshold | Purpose |
|---|---:|
| `MIN_COMPUTE_REPUTATION` | Minimum reputation required to claim/submit compute work |
| `MIN_VERIFY_REPUTATION` | Minimum reputation required to vote as verifier |
| `AUTO_SUSPEND_REPUTATION` | If reputation falls below this value, worker is suspended |

### 7.3 Reputation Deltas

| Event | Effect |
|---|---:|
| Compute fragment verified | `+80` |
| Compute fragment rejected | `-250` |
| Claimed fragment expired | `-120` |
| Correct verifier reward claimed | `+40` |
| Wrong vote | `-180` |
| Slash extra penalty | `-300` |

### 7.4 Current Reputation Behavior

Reputation is updated when:

- a fragment reaches YES quorum and the compute worker is rewarded;
- a fragment reaches NO quorum and the compute worker is penalized;
- a verifier claims a reward for a correct vote;
- a wrong verifier vote is slashed;
- a worker lets a claim expire and the fragment is reclaimed.

Reputation is used as an access-control condition:

- a worker with too little reputation cannot claim or submit compute work;
- a verifier with too little reputation cannot vote;
- a worker can be automatically suspended if reputation becomes too low.

### 7.5 Reputation Event

```rust
WorkerReputationUpdated {
    worker,
    old_reputation,
    new_reputation,
    delta,
    reason,
    status,
}
```

Reason codes:

| Code | Reason |
|---:|---|
| `1` | Compute success |
| `2` | Compute failure |
| `3` | Claim timeout |
| `4` | Vote correct |
| `5` | Vote wrong |
| `6` | Slash |

---

## 8. On-Chain Instructions

### 8.1 `register_worker`

Creates a `Worker` account for the signer.

Effects:

- initializes the worker account;
- sets the owner to the signer;
- initializes empty stake fields;
- sets reputation to `REPUTATION_START` (`5_000`);
- initializes `active_claims` to `0`;
- assigns compute and verify roles by default;
- sets status to `Active`;
- emits `WorkerRegistered`.

### 8.2 `stake_worker(amount)`

Transfers SPL tokens from the worker token account into the worker stake vault.

Requirements:

- `amount > 0`;
- worker account belongs to the signer;
- worker is active;
- worker token account has the expected owner and mint.

Effects:

- initializes the stake vault if needed;
- transfers tokens into the stake vault;
- increases `worker_account.stake_amount`;
- emits `WorkerStaked`.

### 8.3 `init_treasury`

Initializes the treasury configuration and treasury token account for a given mint.

Effects:

- creates the treasury state PDA;
- creates the treasury token account;
- stores the admin, mint, treasury authority, and treasury token account;
- emits `TreasuryInitialized`.

### 8.4 `create_job(...)`

Creates a new job and funds its escrow.

Parameters:

```text
job_id: u64
expected_fragments: u32
reward_per_fragment: u64
verifier_reward_per_vote: u64
verifier_reward_budget: u64
deadline_unix: i64
fragment_quorum: u16
```

Requirements:

- `expected_fragments > 0`;
- `expected_fragments <= MAX_FRAGMENTS_PER_JOB`;
- `reward_per_fragment > 0`;
- `MIN_FRAGMENT_QUORUM <= fragment_quorum <= MAX_FRAGMENT_QUORUM`;
- job TTL must be between `MIN_JOB_TTL_SECS` and `MAX_JOB_TTL_SECS`;
- verifier budget must cover all expected fragment votes:

```text
verifier_reward_budget >= expected_fragments * fragment_quorum * verifier_reward_per_vote
```

- total deposit must be at least `MIN_JOB_DEPOSIT`.

Effects:

- creates the `Job` account;
- transfers the total required amount into escrow;
- stores payment and quorum parameters;
- emits `JobCreated`.

### 8.5 `claim_fragment(fragment_index)`

Allows a worker to reserve a fragment before computing it.

Requirements:

- job is open;
- `fragment_index < expected_fragments`;
- worker has compute role;
- worker is active;
- worker has the minimum required compute stake;
- worker has the minimum required compute reputation;
- worker has fewer than `MAX_ACTIVE_CLAIMS_PER_WORKER` active claims;
- fragment is `Available`, `Rejected`, or an expired `Claimed` fragment.

Effects:

- initializes the fragment account if needed;
- assigns the worker to `assigned_worker`;
- sets `claim_deadline_unix`;
- sets status to `Claimed`;
- increments `worker_account.active_claims`;
- emits `FragmentClaimed`.

### 8.6 `reclaim_fragment(fragment_index)`

Releases an expired claimed fragment and makes it available again.

Requirements:

- job is open;
- fragment status is `Claimed`;
- current on-chain time is greater than or equal to `claim_deadline_unix`;
- `previous_worker_account` must match `fragment.assigned_worker`.

Effects:

- penalizes the previous worker reputation;
- decrements `previous_worker_account.active_claims`;
- clears `assigned_worker`;
- clears `claim_deadline_unix`;
- sets status back to `Available`;
- emits `FragmentReclaimed`.

### 8.7 `submit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits the result of a claimed fragment.

Requirements:

- job is open;
- current time is not past the job deadline;
- fragment is `Claimed`;
- signer is the assigned worker;
- worker has compute role;
- worker is active;
- worker has minimum stake;
- worker has minimum compute reputation;
- claim has not expired.

Effects:

- stores the worker and worker token account;
- stores `result_hash` and `proof_ref`;
- sets status to `Submitted`;
- resets vote counters;
- sets `voting_deadline_unix = now + VOTING_TTL_SECS`;
- increments `worker_account.total_submitted`;
- decrements `worker_account.active_claims`;
- emits `FragmentSubmitted` with `is_resubmission = false`.

### 8.8 `resubmit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a new result for a previously rejected fragment.

Requirements:

- job is open;
- current time is not past the job deadline;
- fragment status is `Rejected`;
- worker has compute role;
- worker is active;
- worker has minimum stake;
- worker has minimum compute reputation.

Effects:

- increments the fragment round;
- resets vote counters;
- stores the new worker, token account, result hash, and proof reference;
- sets status to `Submitted`;
- sets `voting_deadline_unix = now + VOTING_TTL_SECS`;
- increments `worker_account.total_submitted`;
- emits `FragmentSubmitted` with `is_resubmission = true`.

### 8.9 `vote_fragment(choice)`

Allows a verifier to vote on a submitted fragment.

Parameter:

```text
choice: bool
true  => YES, result is valid
false => NO, result is invalid
```

Required accounts added/used by the latest architecture:

- `verifier_worker`;
- `compute_worker`;
- `vote`;
- `round_resolution`;
- `worker_token`.

Requirements:

- job is open;
- fragment belongs to the job;
- fragment status is `Submitted`;
- verifier has verify role;
- verifier is active;
- verifier has minimum verifier stake;
- verifier has minimum verifier reputation;
- verifier is not the submitting worker;
- verifier is not the job client;
- verifier has not already voted for this fragment and round;
- current time is before `fragment.voting_deadline_unix`;
- current time is before `job.deadline_unix`;
- `worker_token` matches `fragment.worker_token_account`;
- `worker_token.owner == fragment.worker`;
- `worker_token.mint == job.mint`;
- `round_resolution` matches the fragment and current round.

Effects when YES quorum is reached:

- marks the fragment as `Verified`;
- increments `job.verified_fragments`;
- pays the worker from escrow;
- creates or updates the round resolution;
- makes winning verifier rewards claimable;
- increases compute worker reputation;
- emits `FragmentVerified`.

Effects when NO quorum is reached:

- marks the fragment as `Rejected`;
- creates or updates the round resolution;
- makes winning verifier rewards claimable;
- decreases compute worker reputation;
- emits `FragmentRejected`.

### 8.10 `claim_verifier_reward`

Allows a verifier who voted with the winning side to claim their reward.

Requirements:

- the vote exists;
- the vote belongs to the signer;
- the vote has not already been claimed;
- the corresponding resolution is resolved;
- the vote round matches the resolution round;
- the resolution fragment matches the target fragment;
- the verifier voted for the winning side;
- there are remaining eligible rewards in the resolution.

Effects:

- transfers `verifier_reward_per_vote` from escrow to the verifier token account;
- marks the vote as claimed;
- increments claimed reward counters;
- increases verifier reputation;
- emits `VerifierRewardClaimed`.

### 8.11 `finalize_job(final_hash, output_uri)`

Finalizes a job and stores the final result reference.

Requirements:

- signer is the job client;
- job is open;
- all expected fragments are verified;
- all claimable verifier rewards have been claimed;
- `output_uri` length is within the maximum allowed size.

Effects:

- creates the `JobResult` account;
- stores `final_hash` and `output_uri`;
- refunds the remaining escrow balance to the client;
- marks the job as `Finalized`;
- emits `JobFinalized`.

### 8.12 `cancel_job`

Cancels a job and refunds the remaining escrow balance.

Requirements:

- signer is the job client;
- job is open;
- cancellation conditions are satisfied by the program logic.

Effects:

- refunds remaining escrow balance;
- marks job as `Cancelled`;
- emits `JobCancelled`.

### 8.13 `slash_vote`

Slashes a verifier for an incorrect vote.

Requirements:

- target vote exists;
- fragment belongs to the job;
- target round is resolved;
- vote round matches the resolution round;
- vote is incorrect compared to the resolved winning choice;
- vote has not already been slashed;
- verifier has enough slashable stake;
- treasury is initialized for the stake mint.

Effects:

- transfers the slash amount from the verifier stake vault to treasury;
- updates verifier stake amount;
- marks the vote as slashed;
- decreases verifier reputation for wrong vote;
- applies extra slash reputation penalty;
- emits `VoteSlashed`.

### 8.14 `init_staking_pool`

Initializes passive network staking for one SPL mint.

Requirements:

- pool PDA does not already exist;
- `stake_vault` and `reward_vault` are initialized with the pool authority.

Effects:

- creates the `StakingPool` account;
- creates stake and reward vaults;
- sets `total_staked = 0`;
- sets `acc_reward_per_share = 0`;
- emits `StakingPoolInitialized`.

### 8.15 `stake_network(amount)`

Allows a passive user to stake tokens in the network pool.

Requirements:

- `amount >= MIN_NETWORK_STAKE`;
- pool exists for the mint;
- owner token account belongs to the signer;
- owner token account has the correct mint;
- stake vault matches the pool.

Effects:

- initializes `NetworkStaker` if needed;
- updates pending rewards before modifying stake;
- transfers tokens from the user to the pool stake vault;
- increases `staker.stake_amount`;
- increases `pool.total_staked`;
- refreshes `reward_debt`;
- emits `NetworkStakeDeposited`.

### 8.16 `fund_staking_rewards(amount)`

Funds passive staking rewards.

Requirements:

- `amount > 0`;
- pool exists;
- `pool.total_staked > 0`;
- funder token account belongs to the signer;
- funder token account has the correct mint;
- reward vault matches the pool.

Effects:

- transfers reward tokens into `reward_vault`;
- updates `pool.acc_reward_per_share` using fixed-point accounting;
- emits `StakingRewardsFunded`.

Formula:

```text
acc_reward_per_share += amount * REWARD_SCALE / total_staked
```

### 8.17 `claim_staking_reward`

Claims passive staking rewards.

Requirements:

- staker belongs to the signer;
- staker mint matches the pool mint;
- reward vault matches the pool;
- pending reward amount is greater than zero.

Effects:

- transfers pending reward from `reward_vault` to the staker token account;
- resets `pending_rewards` to zero;
- refreshes `reward_debt`;
- emits `StakingRewardClaimed`.

### 8.18 `request_unstake(amount)`

Starts the passive unstake process.

Requirements:

- `amount > 0`;
- staker belongs to the signer;
- staker has at least `amount` active passive stake.

Effects:

- updates pending rewards before reducing stake;
- decreases `staker.stake_amount`;
- decreases `pool.total_staked`;
- increases `unstake_requested_amount`;
- sets `unstake_available_at = now + UNSTAKE_COOLDOWN_SECS`;
- refreshes `reward_debt`;
- emits `NetworkUnstakeRequested`.

### 8.19 `withdraw_unstaked`

Withdraws passive stake after the cooldown.

Requirements:

- `unstake_requested_amount > 0`;
- current on-chain time is greater than or equal to `unstake_available_at`;
- pool stake vault has enough tokens.

Effects:

- transfers tokens from the pool stake vault back to the owner;
- resets `unstake_requested_amount` to zero;
- resets `unstake_available_at` to zero;
- emits `NetworkUnstakeWithdrawn`.

---

## 9. State Lifecycles

### 9.1 Job Lifecycle

```text
Open
 ├── Finalized
 └── Cancelled
```

A finalized or cancelled job cannot be used for new fragment submissions or votes.

### 9.2 Fragment Lifecycle

```text
Available
   └── Claimed
         ├── Submitted
         │     ├── Verified
         │     └── Rejected
         │           └── Submitted again through resubmit_fragment_result
         └── Available again through reclaim_fragment if claim expired
```

The `round` field increases when a rejected fragment is resubmitted.

### 9.3 Passive Staker Lifecycle

```text
No account
   └── stake_network
         └── Active stake
               ├── claim_staking_reward
               └── request_unstake
                     └── Cooldown
                           └── withdraw_unstaked
```

---

## 10. Anchor Events

The SDK and backend indexer should consume Anchor events instead of constantly refetching all accounts.

| Event | Purpose |
|---|---|
| `JobCreated` | A job was created and funded |
| `WorkerRegistered` | A worker or verifier identity was created |
| `WorkerStaked` | A worker added active stake |
| `WorkerReputationUpdated` | A worker/verifier reputation changed |
| `TreasuryInitialized` | Treasury was initialized for a mint |
| `FragmentClaimed` | A worker claimed a fragment |
| `FragmentReclaimed` | An expired claim was released |
| `FragmentSubmitted` | A fragment result was submitted or resubmitted |
| `FragmentVerified` | A fragment reached YES quorum |
| `FragmentRejected` | A fragment reached NO quorum |
| `VerifierRewardClaimed` | A verifier claimed a winning reward |
| `JobFinalized` | A job was finalized |
| `JobCancelled` | A job was cancelled |
| `VoteSlashed` | An incorrect vote was slashed |
| `StakingPoolInitialized` | Passive staking pool was initialized |
| `NetworkStakeDeposited` | Passive staker deposited tokens |
| `StakingRewardsFunded` | Rewards were added to the passive staking pool |
| `StakingRewardClaimed` | Passive staker claimed rewards |
| `NetworkUnstakeRequested` | Passive staker requested unstake |
| `NetworkUnstakeWithdrawn` | Passive staker withdrew after cooldown |

Recommended TypeScript SDK event names:

| Anchor event | SDK event name |
|---|---|
| `JobCreated` | `jobCreated` |
| `WorkerRegistered` | `workerRegistered` |
| `WorkerStaked` | `workerStaked` |
| `WorkerReputationUpdated` | `workerReputationUpdated` |
| `TreasuryInitialized` | `treasuryInitialized` |
| `FragmentClaimed` | `fragmentClaimed` |
| `FragmentReclaimed` | `fragmentReclaimed` |
| `FragmentSubmitted` | `fragmentSubmitted` |
| `FragmentVerified` | `fragmentVerified` |
| `FragmentRejected` | `fragmentRejected` |
| `VerifierRewardClaimed` | `verifierRewardClaimed` |
| `JobFinalized` | `jobFinalized` |
| `JobCancelled` | `jobCancelled` |
| `VoteSlashed` | `voteSlashed` |
| `StakingPoolInitialized` | `stakingPoolInitialized` |
| `NetworkStakeDeposited` | `networkStakeDeposited` |
| `StakingRewardsFunded` | `stakingRewardsFunded` |
| `StakingRewardClaimed` | `stakingRewardClaimed` |
| `NetworkUnstakeRequested` | `networkUnstakeRequested` |
| `NetworkUnstakeWithdrawn` | `networkUnstakeWithdrawn` |

---

## 11. TypeScript SDK

The SDK should wrap PDA derivation, account fetching, instruction calls, and event listeners.

### 11.1 Local Installation

Recommended location:

```text
solana-layer/sdk
```

Build commands:

```bash
cd sdk
yarn install
yarn build
```

The Anchor program must be rebuilt after event or instruction changes:

```bash
anchor build
```

### 11.2 Initialization

Example:

```ts
import { SiliciumLayerSdk } from "./sdk";

const sdk = new SiliciumLayerSdk({
  connection,
  wallet,
  programId,
  idl,
});
```

### 11.3 Main SDK Methods

Recommended public methods:

```ts
sdk.registerWorker()
sdk.stakeWorker(amount, mint, workerToken)
sdk.initTreasury(mint)
sdk.createJob(params)
sdk.claimFragment(job, fragmentIndex, workerToken)
sdk.reclaimFragment(job, fragmentIndex, previousWorkerAccount)
sdk.submitFragmentResult(job, fragmentIndex, resultHash, proofRef, workerToken)
sdk.resubmitFragmentResult(job, fragmentIndex, resultHash, proofRef, workerToken)
sdk.voteFragment(job, fragmentIndex, choice)
sdk.claimVerifierReward(params)
sdk.finalizeJob(job, finalHash, outputUri)
sdk.cancelJob(job)
sdk.slashVote(params)

sdk.initStakingPool(mint)
sdk.stakeNetwork(amount, mint, ownerToken)
sdk.fundStakingRewards(amount, mint, funderToken)
sdk.claimStakingReward(mint, ownerRewardToken)
sdk.requestUnstake(amount, mint)
sdk.withdrawUnstaked(mint, ownerToken)
```

### 11.4 Fetch Helpers

Recommended helpers:

```ts
sdk.fetchJob(jobPda)
sdk.fetchFragment(fragmentPda)
sdk.fetchWorker(workerPda)
sdk.fetchVote(votePda)
sdk.fetchResolution(resolutionPda)
sdk.fetchJobResult(resultPda)
sdk.fetchTreasury(treasuryPda)
sdk.fetchStakingPool(poolPda)
sdk.fetchNetworkStaker(stakerPda)
```

### 11.5 PDA Helpers

Recommended helpers:

```ts
sdk.pdas.job(client, jobId)
sdk.pdas.escrowAuth(job)
sdk.pdas.fragment(job, fragmentIndex)
sdk.pdas.worker(owner)
sdk.pdas.stakeAuth(workerAccount)
sdk.pdas.stakeVault(worker)
sdk.pdas.fragmentVote(fragment, verifier, round)
sdk.pdas.fragmentResolution(fragment, round)
sdk.pdas.jobResult(job)
sdk.pdas.treasury(mint)
sdk.pdas.treasuryAuth(mint)
sdk.pdas.stakingPool(mint)
sdk.pdas.stakingPoolAuth(mint)
sdk.pdas.networkStaker(owner, mint)
```

---

## 12. Example SDK Flows

### 12.1 Worker Registration and Stake

```ts
await sdk.registerWorker();
await sdk.stakeWorker(new BN(1_000_000), mint, workerTokenAccount);
```

### 12.2 Client Creates a Job

```ts
await sdk.createJob({
  jobId: new BN(1),
  expectedFragments: 2,
  rewardPerFragment: new BN(1_000_000),
  verifierRewardPerVote: new BN(100_000),
  verifierRewardBudget: new BN(400_000),
  deadlineUnix: new BN(Math.floor(Date.now() / 1000) + 3600),
  fragmentQuorum: 2,
  mint,
  clientTokenAccount,
});
```

### 12.3 Worker Claims and Submits a Fragment

```ts
await sdk.claimFragment(jobPda, 0, workerTokenAccount);

await sdk.submitFragmentResult(
  jobPda,
  0,
  resultHash,
  proofRef,
  workerTokenAccount
);
```

### 12.4 Verifier Votes

```ts
await sdk.voteFragment(jobPda, 0, true);
```

### 12.5 Verifier Claims Reward

```ts
await sdk.claimVerifierReward({
  job: jobPda,
  fragment: fragmentPda,
  vote: votePda,
  resolution: resolutionPda,
  verifierWorker,
  verifierTokenAccount,
});
```

### 12.6 Client Finalizes the Job

```ts
await sdk.finalizeJob(jobPda, finalHash, "ipfs://output-uri");
```

### 12.7 Passive Network Staking Flow

```ts
await sdk.initStakingPool(mint);

await sdk.stakeNetwork(
  new BN(2_000_000),
  mint,
  stakerTokenAccount
);

await sdk.fundStakingRewards(
  new BN(1_000_000),
  mint,
  funderTokenAccount
);

await sdk.claimStakingReward(
  mint,
  stakerRewardTokenAccount
);

await sdk.requestUnstake(
  new BN(1_000_000),
  mint
);

// after cooldown
await sdk.withdrawUnstaked(
  mint,
  stakerTokenAccount
);
```

---

## 13. Recommended Backend Indexing Model

The backend should listen to events and maintain a database projection of the program state.

### `jobs`

| Column | Source |
|---|---|
| `job_pubkey` | `JobCreated.job` |
| `client` | `JobCreated.client` |
| `mint` | `JobCreated.mint` |
| `expected_fragments` | `JobCreated.expected_fragments` |
| `verified_fragments` | `FragmentVerified.verified_fragments` |
| `status` | `JobCreated`, `JobFinalized`, `JobCancelled` |
| `deadline_unix` | `JobCreated.deadline_unix` |

### `fragments`

| Column | Source |
|---|---|
| `fragment_pubkey` | fragment events |
| `job_pubkey` | fragment events |
| `fragment_index` | fragment events |
| `worker` | `FragmentClaimed`, `FragmentSubmitted` |
| `status` | fragment lifecycle events |
| `round` | fragment events |
| `result_hash` | `FragmentSubmitted` |
| `proof_ref` | `FragmentSubmitted` |

### `workers`

| Column | Source |
|---|---|
| `worker` | `WorkerRegistered.worker` |
| `worker_account` | `WorkerRegistered.worker_account` |
| `roles` | `WorkerRegistered.roles` |
| `status` | `WorkerRegistered.status`, `WorkerReputationUpdated.status` |
| `stake_amount` | `WorkerStaked.total_stake`, account fetch after slash |
| `reputation` | `WorkerReputationUpdated.new_reputation` |
| `active_claims` | account fetch after claim, submit, or reclaim |

### `votes`

| Column | Source |
|---|---|
| `fragment` | `FragmentVerified`, `FragmentRejected`, `VoteSlashed` |
| `verifier` | vote-related events |
| `round` | vote-related events |
| `choice` | fetched from `FragmentVote` if needed |
| `reward_claimed` | `VerifierRewardClaimed` |
| `slashed` | `VoteSlashed` |

### `staking_pools`

| Column | Source |
|---|---|
| `pool` | `StakingPoolInitialized.pool` |
| `mint` | `StakingPoolInitialized.mint` |
| `stake_vault` | `StakingPoolInitialized.stake_vault` |
| `reward_vault` | `StakingPoolInitialized.reward_vault` |
| `total_staked` | `NetworkStakeDeposited`, `NetworkUnstakeRequested` |
| `acc_reward_per_share` | `StakingRewardsFunded` |

### `network_stakers`

| Column | Source |
|---|---|
| `staker` | `NetworkStakeDeposited.staker` |
| `owner` | staking events |
| `mint` | account fetch |
| `stake_amount` | `NetworkStakeDeposited`, `NetworkUnstakeRequested` |
| `pending_rewards` | account fetch after staking/reward/claim |
| `unstake_requested_amount` | `NetworkUnstakeRequested`, `NetworkUnstakeWithdrawn` |
| `unstake_available_at` | `NetworkUnstakeRequested`, `NetworkUnstakeWithdrawn` |

---

## 14. Security Invariants

### 14.1 Worker Payments

A worker can only be paid when:

- the fragment is submitted;
- the verifier YES quorum is reached;
- the fragment transitions to `Verified`;
- escrow contains enough tokens;
- `worker_token.owner == fragment.worker`;
- `worker_token.mint == job.mint`.

### 14.2 Verifier Payments

A verifier reward can only be claimed when:

- the round is resolved;
- the vote round matches the resolution round;
- the verifier voted with the winning side;
- the vote has not already been claimed;
- the eligible reward limit has not been exceeded.

### 14.3 Double-Vote Protection

The vote PDA includes:

```text
fragment + verifier + round
```

This prevents one verifier from voting twice on the same fragment round.

### 14.4 Self-Vote and Client-Vote Protection

The worker who submitted the result cannot vote on that same fragment.

The job client cannot vote on their own job.

### 14.5 Expired Claim Reclaim

A claimed fragment can be reclaimed only when the on-chain clock reaches the claim deadline.

Testing should rely on retrying the instruction until the program accepts it, rather than comparing JavaScript `Date.now()` to the on-chain clock.

### 14.6 Finalization Reward Lock

A job cannot be finalized while verifier rewards remain claimable but unclaimed.

This prevents the client from draining escrow before verifiers are paid.

### 14.7 Job Anti-Spam Limits

Job creation is protected by:

- minimum deposit;
- maximum fragment count;
- minimum and maximum job TTL;
- verifier budget coverage check;
- quorum bounds.

### 14.8 Active Claim Limit

A worker can only have a limited number of active fragment claims.

This reduces the risk of a malicious worker claiming many fragments and letting them all expire.

### 14.9 Voting Deadline Isolation

The fragment voting deadline is now separated from the job deadline.

```text
fragment.voting_deadline_unix = submission_time + VOTING_TTL_SECS
```

This prevents a submitted fragment from staying votable for the full job lifetime.

### 14.10 Passive Staking Accounting

Passive staking uses accumulated reward-per-share accounting.

This avoids looping over all stakers and allows proportional reward distribution with O(1) account updates.

### 14.11 Passive Unstake Cooldown

Passive stakers cannot withdraw immediately after requesting unstake.

This prevents short-term reward extraction patterns such as staking just before a distribution and withdrawing instantly.

---

## 15. Anchor Tests

The current test suite covers:

- worker registration;
- worker staking;
- job creation and escrow funding;
- fragment claim;
- fragment result submission;
- verifier registration and staking;
- voting before quorum;
- YES quorum and worker payment;
- NO quorum and fragment rejection;
- fragment resubmission after rejection;
- job finalization;
- expired claim reclaim;
- reputation initialization;
- reputation increase on verified compute;
- reputation decrease on rejected compute;
- verifier reputation increase on reward claim;
- reputation decrease on expired claim;
- incorrect vote slashing;
- job anti-spam limits;
- short-deadline rejection;
- unstaked worker claim rejection;
- unstaked verifier vote rejection;
- client self-verification rejection;
- compute worker self-vote rejection;
- double slash rejection;
- passive staking pool initialization;
- passive network stake deposit;
- reward funding rejection when no stakers exist;
- passive reward funding and claim;
- reward claim rejection when there are no rewards;
- unstake request and early withdraw rejection;
- unstaked withdrawal after cooldown;
- withdrawal rejection when there is nothing to withdraw.

Run tests with:

```bash
anchor test
```

If a test uses a time-based cooldown, prefer retry loops over fixed sleeps because the Solana test validator clock may not match JavaScript wall-clock time exactly.

---

## 16. Production Readiness Notes

### 16.1 `CLAIM_TTL_SECS`

The current claim TTL is short for tests. For production, it should be configurable or significantly increased.

### 16.2 `UNSTAKE_COOLDOWN_SECS`

The passive unstake cooldown is currently short for local testing. For a real network, it should be increased.

### 16.3 Role Management

Workers are currently registered with compute and verify roles by default. For production, role assignment should likely be controlled, configurable, or permissioned by governance.

### 16.4 Reputation Separation

The current reputation model uses one score for both compute and verify behavior.

A future version should split it into:

```text
compute_reputation
verify_reputation
global_reputation
```

### 16.5 Verifier Reward Claims

Verifier rewards are claimed individually. For better UX, the SDK or backend can provide batched reward claiming.

### 16.6 Worker Reward Payment Timing

The current MVP pays a worker immediately when a YES quorum is reached.

A more advanced architecture could make worker rewards claimable separately through a `claim_worker_reward` instruction, enabling challenge periods before payment.

### 16.7 Challenge Period

The current MVP finalizes a fragment immediately after quorum. A future version could add a challenge window before a fragment becomes fully verified.

### 16.8 Slashing

The slashing flow should be audited carefully. The project should define:

- slash percentage;
- minimum slash amount;
- maximum slash amount;
- appeal or dispute policy, if any;
- how reputation changes after slashing;
- whether delegated stake should ever be slashable.

### 16.9 Passive Staking Risk Model

Passive stakers are not slashable in the current V1 because they do not compute or verify.

A future delegation model could let stakers delegate to verifiers, with partial slash risk if the delegated verifier misbehaves.

### 16.10 Final Result Storage

The on-chain program stores only a final hash and a short output URI. Large outputs should remain off-chain, for example in IPFS, Arweave, S3, or another storage layer.

### 16.11 Program ID Sync

If Anchor reports a mismatch such as:

```text
Program ID mismatch detected
```

run:

```bash
anchor keys sync
```

then rebuild.

---

## 17. Useful Commands

### Build

```bash
anchor build
```

### Test

```bash
anchor test
```

### Clean and Rebuild

```bash
anchor clean
rm -rf target
anchor build
anchor test
```

### Sync Program ID

```bash
anchor keys sync
```

### Start a Local Validator

```bash
solana-test-validator
```

### Generate the IDL

```bash
anchor build
```

### Rebuild the SDK

```bash
cd sdk
yarn install
yarn build
```

---

## 18. Project Integration Summary

For the rest of the Silicium project, the Solana Layer should be treated as the source of truth for:

- job creation and funding;
- fragment lifecycle state;
- worker and verifier economic guarantees;
- worker reputation;
- result validation;
- worker payments;
- verifier rewards;
- slashing;
- job finalization;
- passive network staking;
- passive staking rewards and cooldown withdrawals.

The backend and SDK should use Anchor events to keep an indexed view of the network state and only refetch accounts when additional fields are needed.

Recommended integration stack:

```text
Frontend / Dashboard
        │
        ▼
TypeScript SDK
        │
        ▼
Solana Layer Anchor Program
        │
        ▼
Event Indexer / Backend Database
        │
        ▼
Off-chain Worker Network
```

---

## 19. Session Work Summary

During this work session, the Solana Layer was upgraded with:

1. A functional reputation system.
2. Reputation-based access control for compute and verify roles.
3. Reputation rewards and penalties for compute success/failure, verifier correctness, slash, and expired claims.
4. Job anti-spam limits.
5. Separate voting deadlines per fragment submission.
6. Active claim limits per worker.
7. Stronger vote, reward, and slash account constraints.
8. Client self-verification protection.
9. Passive network staking architecture.
10. Passive staking reward accounting with `acc_reward_per_share`.
11. Passive unstake request and cooldown withdrawal.
12. Additional tests for reputation, security invariants, slashing, and passive staking.

