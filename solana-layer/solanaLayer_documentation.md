# Technical Documentation — Silicium Solana Layer

Version: 0.1  
Project: **Silicium / EIP**  
Anchor program: `solana-layer`  
Current Program ID: `Ezt3UKgn7o1uoFmnG2zhKXW9NoygJMwJ3FErNUczy9jj`

---

## 1. Purpose of the Solana Layer

The **Solana Layer** is the on-chain settlement and validation layer of the Silicium project.

It does not execute distributed computation directly. Computation is performed off-chain by workers. The Solana program manages the economic guarantees, job state, fragment state, validation votes, escrowed payments, verifier rewards, cancellation, finalization, and slashing.

The program is responsible for:

- registering workers and verifiers;
- staking SPL tokens before participating in the network;
- creating jobs funded through an escrow token account;
- splitting jobs into fragments;
- allowing workers to claim fragments;
- allowing workers to submit fragment results;
- allowing verifiers to vote on submitted results;
- paying workers when a fragment reaches a positive quorum;
- making verifier rewards claimable after a winning vote;
- rejecting and resubmitting fragments;
- reclaiming expired fragment claims;
- finalizing or cancelling jobs;
- slashing incorrect votes.

---

## 2. High-Level Architecture

The Solana Layer is built around three main objects:

1. **Jobs** — computation tasks submitted by a client and funded in advance.
2. **Fragments** — smaller units of work derived from a job.
3. **Votes** — verifier decisions on submitted fragment results.

Main flow:

```text
Client
  └── create_job
        └── SPL escrow funded
              └── worker claim_fragment
                    └── worker submit_fragment_result
                          └── verifiers vote_fragment
                                ├── YES quorum => fragment verified + worker paid
                                └── NO quorum  => fragment rejected
                                      └── resubmit_fragment_result possible
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

### 3.2 Worker

A worker is a machine that executes computation fragments off-chain.

A worker must:

- be registered through `register_worker`;
- have the compute role;
- be active;
- have the minimum required stake;
- claim a fragment before submitting a result.

### 3.3 Verifier

A verifier checks submitted fragment results and votes on them.

A verifier must:

- be registered through `register_worker`;
- have the verify role;
- be active;
- have the minimum required stake;
- not be the worker who submitted the fragment.

### 3.4 Slasher

The slasher can be any signer. The slasher calls `slash_vote` when a verifier vote is incorrect relative to the resolved result of the fragment round.

---

## 4. Main Accounts

### 4.1 `Job`

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
| `deadline_unix` | Global job deadline |
| `fragment_quorum` | Required quorum per fragment |
| `status` | `Open`, `Finalized`, or `Cancelled` |

PDA:

```text
[b"job", client, job_id_le_u64]
```

### 4.2 `Fragment`

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
| `voting_deadline_unix` | Vote deadline |
| `round` | Current fragment round |

PDA:

```text
[b"fragment", job, fragment_index_le_u32]
```

### 4.3 `Worker`

The `Worker` account stores the identity, role, stake, and reputation state of a worker or verifier.

| Field | Description |
|---|---|
| `owner` | Owner wallet |
| `stake_mint` | SPL mint used for staking |
| `stake_vault` | Token vault holding the stake |
| `stake_amount` | Amount currently staked |
| `reputation` | Reputation score |
| `total_submitted` | Number of submitted results |
| `total_verified` | Number of successful positive verifications |
| `total_rejected` | Number of successful rejections |
| `roles` | Compute and/or verify role flags |
| `status` | Worker status |

PDA:

```text
[b"worker", worker_pubkey]
```

### 4.4 `FragmentVote`

The `FragmentVote` account stores one verifier vote for one fragment and one round.

PDA:

```text
[b"fragment_vote", fragment, verifier, round_le_u16]
```

This PDA prevents a verifier from voting more than once per fragment per round.

### 4.5 `FragmentResolution`

The `FragmentResolution` account stores the final result of a voting round.

PDA:

```text
[b"fragment_resolution", fragment, round_le_u16]
```

It stores:

- the resolved round;
- whether the round is resolved;
- the winning choice;
- how many verifier rewards are eligible;
- how many verifier rewards have already been claimed.

### 4.6 `JobResult`

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

### 4.7 `Treasury`

The `Treasury` account stores the treasury configuration used to receive slashed tokens.

Treasury state PDA:

```text
[b"treasury", mint]
```

Treasury authority PDA:

```text
[b"treasury_auth", mint]
```

---

## 5. PDA Reference

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

---

## 6. On-Chain Instructions

### 6.1 `register_worker`

Creates a `Worker` account for the signer.

Effects:

- initializes the worker account;
- sets the owner to the signer;
- initializes empty stake fields;
- assigns compute and verify roles by default;
- sets the status to active;
- emits `WorkerRegistered`.

### 6.2 `stake_worker(amount)`

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

### 6.3 `init_treasury`

Initializes the treasury configuration and treasury token account for a given mint.

Effects:

- creates the treasury state PDA;
- creates the treasury token account;
- stores the admin, mint, treasury authority, and treasury token account;
- emits `TreasuryInitialized`.

### 6.4 `create_job(...)`

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
- `reward_per_fragment > 0`;
- valid escrow token account;
- valid client token account;
- escrow amount equals worker rewards plus verifier reward budget.

Effects:

- creates the `Job` account;
- transfers the total required amount into escrow;
- stores payment and quorum parameters;
- emits `JobCreated`.

### 6.5 `claim_fragment(fragment_index)`

Allows a worker to reserve a fragment before computing it.

Requirements:

- job is open;
- `fragment_index < expected_fragments`;
- worker has compute role;
- worker is active;
- worker has the minimum required compute stake;
- fragment is `Available`, `Rejected`, or an expired `Claimed` fragment.

Effects:

- initializes the fragment account if needed;
- assigns the worker to `assigned_worker`;
- sets `claim_deadline_unix`;
- sets status to `Claimed`;
- emits `FragmentClaimed`.

### 6.6 `reclaim_fragment(fragment_index)`

Releases an expired claimed fragment and makes it available again.

Requirements:

- job is open;
- fragment status is `Claimed`;
- current on-chain time is greater than or equal to `claim_deadline_unix`.

Effects:

- clears `assigned_worker`;
- clears `claim_deadline_unix`;
- sets status back to `Available`;
- emits `FragmentReclaimed`.

### 6.7 `submit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits the result of a claimed fragment.

Requirements:

- job is open;
- fragment is `Claimed`;
- signer is the assigned worker;
- worker has compute role;
- worker is active;
- worker has minimum stake;
- claim has not expired.

Effects:

- stores the worker and worker token account;
- stores `result_hash` and `proof_ref`;
- sets status to `Submitted`;
- resets vote counters;
- sets voting deadline;
- increments `worker_account.total_submitted`;
- emits `FragmentSubmitted` with `is_resubmission = false`.

### 6.8 `resubmit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a new result for a previously rejected fragment.

Requirements:

- job is open;
- fragment status is `Rejected`;
- worker has compute role;
- worker is active;
- worker has minimum stake.

Effects:

- increments the fragment round;
- resets vote counters;
- stores the new worker, token account, result hash, and proof reference;
- sets status to `Submitted`;
- increments `worker_account.total_submitted`;
- emits `FragmentSubmitted` with `is_resubmission = true`.

### 6.9 `vote_fragment(choice)`

Allows a verifier to vote on a submitted fragment.

Parameter:

```text
choice: bool
true  => YES, result is valid
false => NO, result is invalid
```

Requirements:

- job is open;
- fragment status is `Submitted`;
- verifier has verify role;
- verifier is active;
- verifier has minimum stake;
- verifier is not the submitting worker;
- verifier has not already voted for this fragment and round.

Effects when YES quorum is reached:

- marks the fragment as `Verified`;
- increments `job.verified_fragments`;
- pays the worker from escrow;
- creates or updates the round resolution;
- makes winning verifier rewards claimable;
- emits `FragmentVerified`.

Effects when NO quorum is reached:

- marks the fragment as `Rejected`;
- creates or updates the round resolution;
- makes winning verifier rewards claimable;
- emits `FragmentRejected`.

### 6.10 `claim_verifier_reward`

Allows a verifier who voted with the winning side to claim their reward.

Requirements:

- the vote exists;
- the vote belongs to the signer;
- the vote has not already been claimed;
- the corresponding resolution is resolved;
- the verifier voted for the winning side;
- there are remaining eligible rewards in the resolution.

Effects:

- transfers `verifier_reward_per_vote` from escrow to the verifier token account;
- marks the vote as claimed;
- increments claimed reward counters;
- emits `VerifierRewardClaimed`.

### 6.11 `finalize_job(final_hash, output_uri)`

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

### 6.12 `cancel_job`

Cancels a job and refunds the remaining escrow balance.

Requirements:

- signer is the job client;
- job is open;
- cancellation conditions are satisfied by the program logic.

Effects:

- refunds remaining escrow balance;
- marks job as `Cancelled`;
- emits `JobCancelled`.

### 6.13 `slash_vote`

Slashes a verifier for an incorrect vote.

Requirements:

- target vote exists;
- target round is resolved;
- vote is incorrect compared to the resolved winning choice;
- verifier has enough slashable stake;
- treasury is initialized for the stake mint.

Effects:

- transfers the slash amount from the verifier stake vault to treasury;
- updates verifier stake amount;
- emits `VoteSlashed`.

---

## 7. State Lifecycles

### 7.1 Job Lifecycle

```text
Open
 ├── Finalized
 └── Cancelled
```

A finalized or cancelled job cannot be used for new fragment submissions or votes.

### 7.2 Fragment Lifecycle

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

---

## 8. Anchor Events

The SDK and backend indexer should consume Anchor events instead of constantly refetching all accounts.

Expected event set:

| Event | Purpose |
|---|---|
| `JobCreated` | A job was created and funded |
| `WorkerRegistered` | A worker or verifier identity was created |
| `WorkerStaked` | A worker added stake |
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

Recommended TypeScript SDK event names:

| Anchor event | SDK event name |
|---|---|
| `JobCreated` | `jobCreated` |
| `WorkerRegistered` | `workerRegistered` |
| `WorkerStaked` | `workerStaked` |
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

---

## 9. TypeScript SDK

The SDK should wrap PDA derivation, account fetching, instruction calls, and event listeners.

### 9.1 Local Installation

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

### 9.2 Initialization

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

### 9.3 Main SDK Methods

Recommended public methods:

```ts
sdk.registerWorker()
sdk.stakeWorker(amount, mint, workerToken)
sdk.initTreasury(mint)
sdk.createJob(params)
sdk.claimFragment(job, fragmentIndex, workerToken)
sdk.reclaimFragment(job, fragmentIndex)
sdk.submitFragmentResult(job, fragmentIndex, resultHash, proofRef, workerToken)
sdk.resubmitFragmentResult(job, fragmentIndex, resultHash, proofRef, workerToken)
sdk.voteFragment(job, fragmentIndex, choice)
sdk.claimVerifierReward(params)
sdk.finalizeJob(job, finalHash, outputUri)
sdk.cancelJob(job)
sdk.slashVote(params)
```

### 9.4 Fetch Helpers

Recommended helpers:

```ts
sdk.fetchJob(jobPda)
sdk.fetchFragment(fragmentPda)
sdk.fetchWorker(workerPda)
sdk.fetchVote(votePda)
sdk.fetchResolution(resolutionPda)
sdk.fetchJobResult(resultPda)
sdk.fetchTreasury(treasuryPda)
```

### 9.5 PDA Helpers

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
```

---

## 10. Example SDK Flow

### 10.1 Worker Registration and Stake

```ts
await sdk.registerWorker();
await sdk.stakeWorker(new BN(1_000_000), mint, workerTokenAccount);
```

### 10.2 Client Creates a Job

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

### 10.3 Worker Claims and Submits a Fragment

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

### 10.4 Verifier Votes

```ts
await sdk.voteFragment(jobPda, 0, true);
```

### 10.5 Verifier Claims Reward

```ts
await sdk.claimVerifierReward({
  job: jobPda,
  fragment: fragmentPda,
  vote: votePda,
  resolution: resolutionPda,
  verifierTokenAccount,
});
```

### 10.6 Client Finalizes the Job

```ts
await sdk.finalizeJob(jobPda, finalHash, "ipfs://output-uri");
```

---

## 11. Recommended Backend Indexing Model

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
| `status` | `WorkerRegistered.status` |
| `stake_amount` | `WorkerStaked.total_stake` |

### `votes`

| Column | Source |
|---|---|
| `fragment` | `FragmentVerified`, `FragmentRejected`, `VoteSlashed` |
| `verifier` | vote-related events |
| `round` | vote-related events |
| `choice` | fetched from `FragmentVote` if needed |
| `reward_claimed` | `VerifierRewardClaimed` |
| `slashed` | `VoteSlashed` |

---

## 12. Security Invariants

### 12.1 Worker Payments

A worker can only be paid when:

- the fragment is submitted;
- the verifier YES quorum is reached;
- the fragment transitions to `Verified`;
- escrow contains enough tokens.

### 12.2 Verifier Payments

A verifier reward can only be claimed when:

- the round is resolved;
- the verifier voted with the winning side;
- the vote has not already been claimed;
- the eligible reward limit has not been exceeded.

### 12.3 Double-Vote Protection

The vote PDA includes:

```text
fragment + verifier + round
```

This prevents one verifier from voting twice on the same fragment round.

### 12.4 Self-Vote Protection

The worker who submitted the result cannot vote on that same fragment.

### 12.5 Expired Claim Reclaim

A claimed fragment can be reclaimed only when the on-chain clock reaches the claim deadline.

Testing should rely on retrying the instruction until the program accepts it, rather than comparing JavaScript `Date.now()` to the on-chain clock.

### 12.6 Finalization Reward Lock

A job cannot be finalized while verifier rewards remain claimable but unclaimed.

This prevents the client from draining escrow before verifiers are paid.

---

## 13. Anchor Tests

The current test suite should cover:

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
- incorrect vote slashing.

Run tests with:

```bash
anchor test
```

---

## 14. Production Readiness Notes

### 14.1 `CLAIM_TTL_SECS`

The current claim TTL is short for tests. For production, it should be configurable or significantly increased.

### 14.2 Role Management

Workers are currently registered with compute and verify roles by default. For production, role assignment should likely be controlled or configurable.

### 14.3 Reputation

The worker account contains reputation fields, but the reputation model should be formalized before production.

### 14.4 Verifier Reward Claims

Verifier rewards are claimed individually. For better UX, the SDK or backend can provide batched reward claiming.

### 14.5 Slashing

The slashing flow should be audited carefully. The project should define:

- slash percentage;
- minimum slash amount;
- maximum slash amount;
- appeal or dispute policy, if any;
- how reputation changes after slashing.

### 14.6 Final Result Storage

The on-chain program stores only a final hash and a short output URI. Large outputs should remain off-chain, for example in IPFS, Arweave, S3, or another storage layer.

---

## 15. Useful Commands

### Build

```bash
anchor build
```

### Test

```bash
anchor test
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

## 16. Project Integration Summary

For the rest of the Silicium project, the Solana Layer should be treated as the source of truth for:

- job creation and funding;
- fragment lifecycle state;
- worker and verifier economic guarantees;
- result validation;
- worker payments;
- verifier rewards;
- slashing;
- job finalization.

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
