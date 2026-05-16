# Technical Documentation — Silicium Solana Layer

Project: **Silicium / EIP**  
Anchor program: `solana-layer`  
Current Devnet Program ID:

```txt
48Bdt8Dg9FW8n6Mpvvdh6dgTXrsBvBfqMrwhnWQ2WQm1
```

Keep the following files and tools aligned with the same Program ID:

```txt
declare_id!(...) in programs/solana-layer/src/lib.rs
Anchor.toml
target/deploy/solana_layer-keypair.json
SDK constants
Devnet smoke tests
Dashboard configuration
```

---

## 1. Purpose of the Solana Layer

The Solana Layer is the on-chain settlement, validation, staking, reputation, reward, storage-reference and slashing layer of Silicium.

It does not execute heavy computation directly. Computation, rendering, simulation, AI inference, scientific workloads and proof generation happen off-chain. The on-chain program manages the trust, economics and lifecycle of that off-chain work.

The program manages:

- job creation and escrow funding;
- job storage metadata declaration;
- fragment and sub-fragment lifecycle;
- worker and verifier registration;
- optional active stake for higher-risk work;
- role-specific reputation;
- result hash submission;
- verifier voting;
- worker payments;
- verifier rewards;
- incorrect vote slashing;
- passive network staking;
- job finalization and cancellation.

The core design is:

```txt
Solana Layer
→ state, payments, reputation, votes, hashes, storage commitments

Off-chain / P2P storage
→ task files, manifests, inputs, outputs, proofs, logs

Workers and verifiers
→ download off-chain data, verify hashes, compute, validate, then interact on-chain
```

---

## 2. High-level architecture

### 2.1 Normal compute flow

```txt
Client
  └── uploads task files / manifest to P2P storage
        └── create_job
              └── declare_job_storage
                    └── escrow funded
                          └── worker fetches storage metadata
                                └── worker downloads manifest and fragment input
                                      └── worker verifies checksums
                                            └── worker claim_fragment
                                                  └── worker computes off-chain
                                                        └── submit_fragment_result(result_hash, proof_ref)
                                                              └── verifiers download result/proof
                                                                    └── verifiers verify checksums + computation
                                                                          └── vote_fragment
                                                                                ├── YES quorum => fragment verified + worker paid + compute reputation increases
                                                                                └── NO quorum  => fragment rejected + compute reputation decreases
```

### 2.2 Split / sub-fragment flow

```txt
Worker claims complex parent fragment
  └── propose_fragment_split(manifest_hash, child_count)
        └── approver approve_fragment_split
              └── create_sub_fragment child 0
              └── create_sub_fragment child 1
              └── create_sub_fragment child N
                    └── parent becomes SplitParent
                          └── children behave like normal leaf fragments
```

The split manifest remains off-chain. The program stores only `manifest_hash`, parent/child relationships, child requirements and lifecycle state.

### 2.3 Storage / P2P flow

```txt
Client prepares task manifest
  └── uploads manifest and input files to P2P/storage layer
        └── computes manifest_hash, input_root_hash, storage_ref_hash
              └── declares JobStorage on-chain
                    └── worker fetches JobStorage
                          └── worker downloads manifest using storage routing data
                                └── worker verifies sha256(manifest) == manifest_hash
                                      └── worker downloads assigned input
                                            └── worker verifies input checksum
                                                  └── worker computes and uploads output/proof
                                                        └── worker submits result_hash + proof_ref on-chain
                                                              └── verifier downloads output/proof and verifies checksums
```

### 2.4 Passive staking flow

```txt
init_staking_pool
  └── stake_network
        └── fund_staking_rewards
              └── claim_staking_reward
                    └── request_unstake
                          └── cooldown
                                └── withdraw_unstaked
```

Passive staking is separate from active worker/verifier stake. Passive stakers do not compute and do not verify.

---

## 3. Actors

### 3.1 Client

The client creates and funds jobs. The client is responsible for preparing the task, uploading off-chain data, declaring storage metadata and finalizing the job once all fragments are verified and verifier rewards are claimed.

The client can:

- create a job;
- declare storage metadata for that job;
- cancel a job under program rules;
- finalize a job;
- recover remaining escrow during finalization or cancellation.

The client cannot vote on their own job.

### 3.2 Compute worker

A compute worker executes assigned fragments off-chain.

Access is controlled by:

```txt
ROLE_COMPUTE
worker.status == Active
worker.compute_reputation
worker.active_claims
fragment.required_compute_reputation
fragment.required_stake
fragment.is_leaf
```

Bootstrap fragments can require zero active stake. Higher-risk, more valuable or split-related fragments can require active stake.

### 3.3 Verifier

A verifier checks submitted fragment results and votes.

Access is controlled by:

```txt
ROLE_VERIFY
worker.status == Active
worker.verify_reputation
not the submitting worker
not the job client
one vote per verifier per fragment round
```

The verifier verifies off-chain data by downloading the result/proof, checking checksums, and validating the computation.

### 3.4 Slasher

Any signer can call `slash_vote` when a verifier vote is incorrect relative to a resolved round.

The slasher does not need to be the client, a worker or a verifier.

### 3.5 Passive network staker

A passive network staker supports the network economically through the staking pool.

Passive stakers can:

- deposit tokens in the passive staking pool;
- accumulate proportional rewards;
- claim rewards;
- request unstake;
- withdraw after cooldown.

Passive stakers do not need a `Worker` account.

### 3.6 Split approver / scheduler

The split approver validates proposed sub-fragmentation.

The approver should verify that the split manifest is safe, bounded and economically coherent before approving the split.

---

## 4. Constants

Important constants:

| Constant | Meaning | Value / note |
|---|---|---:|
| `MIN_COMPUTE_STAKE` | Minimum active stake for normal bootstrap compute | `0` |
| `MIN_VERIFIER_STAKE` | Minimum active stake for verifier bootstrap | `0` |
| `MIN_FRAGMENT_QUORUM` | Minimum verifier quorum | `2` |
| `MAX_FRAGMENT_QUORUM` | Maximum verifier quorum | `10` |
| `MIN_JOB_DEPOSIT` | Minimum total escrow deposit | `1_000_000` |
| `MAX_FRAGMENTS_PER_JOB` | Max fragments in a job | `1_000` |
| `MIN_JOB_TTL_SECS` | Minimum job lifetime | `60` |
| `MAX_JOB_TTL_SECS` | Maximum job lifetime | `7 days` |
| `VOTING_TTL_SECS` | Fragment vote window after submission | `300` |
| `MAX_ACTIVE_CLAIMS_PER_WORKER` | Parallel claim limit | `5` |
| `MIN_NETWORK_STAKE` | Passive staking minimum | `1_000_000` |
| `UNSTAKE_COOLDOWN_SECS` | Passive unstake cooldown | `5` for tests |

Split constants:

| Constant | Meaning | Local/test value |
|---|---|---:|
| `DEFAULT_MAX_FRAGMENT_DEPTH` | Max depth for fragment trees | `4` |
| `DEFAULT_MAX_CHILDREN_PER_FRAGMENT` | Per-parent child cap | `8` |
| `MAX_CHILDREN_PER_SPLIT` | Hard split child cap | `8` |
| `SPLIT_MIN_REPUTATION` | Required compute reputation for split | `5_000` local |
| `SPLIT_MIN_STAKE` | Required stake for split proposal | `1_000` |
| `SPLIT_MIN_COMPLEXITY` | Minimum complexity before split | `1_000` local |
| `DEFAULT_ROOT_COMPLEXITY_SCORE` | Root fragment default complexity | `1_000` |

For beta/mainnet, split reputation and complexity thresholds should be stricter than local values.

---

## 5. Main accounts

### 5.1 `Job`

A `Job` stores task payment and global state.

PDA:

```txt
[b"job", client, job_id_le_u64]
```

Important fields:

| Field | Purpose |
|---|---|
| `job_id` | Client-provided logical ID |
| `client` | Job owner |
| `mint` | SPL mint used for payment |
| `escrow` | Token escrow |
| `expected_fragments` | Number of required leaf fragments |
| `verified_fragments` | Verified leaf fragment count |
| `reward_per_fragment` | Worker reward |
| `verifier_reward_per_vote` | Verifier reward |
| `verifier_reward_budget` | Reserved verifier reward budget |
| `deposited_amount` | Initial deposit |
| `paid_amount` | Already paid amount |
| `claimable_verifier_rewards_total` | Claimable verifier rewards |
| `claimed_verifier_rewards_total` | Claimed verifier rewards |
| `created_at_unix` | Creation timestamp |
| `deadline_unix` | Job deadline |
| `verified_at_unix` | Time when all leaf fragments became verified |
| `fragment_quorum` | Required votes per fragment |
| `status` | Open / Finalized / Cancelled |
| `bump` | Job PDA bump |
| `escrow_auth_bump` | Escrow authority bump |

### 5.2 `JobStorage`

A `JobStorage` account links a job to the off-chain/P2P storage layer.

PDA:

```txt
[b"job_storage", job]
```

Fields:

| Field | Purpose |
|---|---|
| `job` | Parent job |
| `manifest_hash` | SHA-256 hash of the canonical off-chain job manifest |
| `input_root_hash` | Root checksum for all task inputs declared by the manifest |
| `storage_ref_hash` | Hash of the storage routing reference or storage manifest |
| `encryption_ref_hash` | Optional hash of encryption/key-distribution metadata; zero hash means not declared |
| `declared_by` | Client wallet that declared the storage metadata |
| `created_at_unix` | On-chain timestamp |
| `bump` | PDA bump |

`JobStorage` does not store files or raw URIs. It stores integrity commitments that workers and verifiers use to check downloaded data.

### 5.3 `Fragment`

A `Fragment` represents one unit of work.

PDA:

```txt
[b"fragment", job, fragment_index_le_u32]
```

Important fields:

| Field | Purpose |
|---|---|
| `job` | Parent job |
| `fragment_index` | Index inside the job |
| `assigned_worker` | Worker that claimed the fragment |
| `worker` | Worker that submitted the result |
| `worker_token_account` | Payment account for worker reward |
| `result_hash` | Hash of off-chain result |
| `proof_ref` | 32-byte reference to off-chain proof/artifact |
| `status` | Available / Claimed / Submitted / Verified / Rejected / SplitPending / SplitApproved / SplitParent |
| `yes_votes` | YES votes for current round |
| `no_votes` | NO votes for current round |
| `required_quorum` | Quorum for this fragment |
| `claim_deadline_unix` | Worker claim timeout |
| `voting_deadline_unix` | Voting timeout after submission |
| `round` | Current voting/submission round |
| `parent_fragment` | Parent fragment for sub-fragments |
| `depth` | Depth in fragment tree |
| `children_count` | Children already created |
| `max_children` | Child cap |
| `split_manifest_hash` | Hash of off-chain split manifest |
| `splitter_worker` | Worker that proposed split |
| `is_leaf` | Whether fragment is claimable/computable |
| `required_compute_reputation` | Minimum compute score for claim/submit |
| `required_stake` | Per-fragment active stake requirement |
| `complexity_score` | Scheduler/split complexity estimate |

A `SplitParent` is not claimable. Only leaf fragments are claimable.

### 5.4 `SplitProposal`

Stores a request to split a parent fragment.

PDA:

```txt
[b"split_proposal", parent_fragment]
```

Important fields:

| Field | Purpose |
|---|---|
| `job` | Job owning the parent |
| `parent_fragment` | Fragment being split |
| `splitter_worker` | Worker that proposed the split |
| `manifest_hash` | Hash of off-chain split manifest |
| `child_count` | Number of requested children |
| `depth` | Parent depth |
| `approved` | Approval state |
| `rejected` | Rejection state |
| `created_children` | Created child count |
| `bump` | PDA bump |

### 5.5 `Worker`

The `Worker` account stores identity, roles, active stake, reputation, counters and scheduler-oriented scores.

PDA:

```txt
[b"worker", owner]
```

Fields:

| Field | Purpose |
|---|---|
| `owner` | Wallet that owns the worker identity |
| `stake_mint` | Mint used for active worker stake |
| `stake_vault` | Vault holding active stake |
| `stake_amount` | Active stake amount |
| `compute_reputation` | Score used when computing fragments |
| `verify_reputation` | Score used when verifying fragments |
| `global_reputation` | Derived global score for scheduler/dashboard |
| `total_submitted` | Number of submitted results |
| `total_verified` | Successful/verified-related counter |
| `total_rejected` | Rejection/failure-related counter |
| `compute_jobs_done` | Compute-specific success counter |
| `verify_jobs_done` | Verification-specific success counter |
| `compute_failures` | Compute-specific failure counter |
| `verify_failures` | Verification-specific failure counter |
| `active_claims` | Currently claimed fragments |
| `roles` | Compute/verify bit flags |
| `preferred_role` | Scheduler preference only |
| `status` | Active, Suspended, Banned |
| `compute_alpha_long` | Compute long-term Bayesian success memory |
| `compute_beta_long` | Compute long-term Bayesian failure memory |
| `compute_alpha_short` | Compute short-term Bayesian success memory |
| `compute_beta_short` | Compute short-term Bayesian failure memory |
| `verify_alpha_long` | Verify long-term Bayesian success memory |
| `verify_beta_long` | Verify long-term Bayesian failure memory |
| `verify_alpha_short` | Verify short-term Bayesian success memory |
| `verify_beta_short` | Verify short-term Bayesian failure memory |
| `compute_fraud_strikes` | Compute-specific fraud count |
| `verify_fraud_strikes` | Verify-specific fraud count |
| `fraud_strikes` | Aggregate fraud count |
| `error_strikes` | Non-fraud major error count |
| `last_reputation_update` | Last reputation update timestamp |
| `performance_score` | Off-chain scheduler score |
| `efficiency_score` | Proof-of-Efficiency score |
| `reliability_score` | Derived global reliability |
| `bump` | PDA bump |

Roles:

```txt
ROLE_COMPUTE = 1
ROLE_VERIFY  = 2
```

Optional scheduler preference:

```txt
ROLE_AUTO = 0
ROLE_COMPUTE_PREFERRED = 1
ROLE_VERIFY_PREFERRED = 2
```

### 5.6 Other accounts

#### `FragmentVote`

PDA:

```txt
[b"fragment_vote", fragment, verifier, round_le_u16]
```

Stores one verifier vote for one fragment round.

#### `FragmentResolution`

PDA:

```txt
[b"fragment_resolution", fragment, round_le_u16]
```

Stores the final winning side and eligible verifier reward count.

#### `JobResult`

PDA:

```txt
[b"result", job]
```

Stores the final hash and output URI.

#### `Treasury`

Receives slashed active stake.

#### `StakingPool` and `NetworkStaker`

Used for passive network staking and reward distribution.

---

## 6. PDA reference

| Object | Seeds |
|---|---|
| Job | `[b"job", client, job_id_le_u64]` |
| Job storage | `[b"job_storage", job]` |
| Escrow authority | `[b"escrow_auth", job]` |
| Fragment | `[b"fragment", job, fragment_index_le_u32]` |
| Split proposal | `[b"split_proposal", parent_fragment]` |
| Worker | `[b"worker", owner]` |
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

## 7. Storage and hash management

### 7.1 Storage responsibility split

Silicium separates data storage from settlement:

```txt
Solana
→ hashes, references, lifecycle state, economic settlement

P2P/storage layer
→ task manifests, input files, result files, proof files, logs
```

The on-chain program never stores large files. It stores enough commitments to verify that off-chain data has not changed.

### 7.2 Job manifest

The job manifest is a canonical JSON document describing the task and all input fragments.

Example:

```json
{
  "version": 1,
  "job_type": "render_3d",
  "created_by": "wallet_or_backend_id",
  "fragments": [
    {
      "fragment_index": 0,
      "input_uri": "p2p://fragment-0",
      "input_sha256": "...",
      "size": 123456,
      "mime": "application/octet-stream"
    },
    {
      "fragment_index": 1,
      "input_uri": "p2p://fragment-1",
      "input_sha256": "...",
      "size": 456789,
      "mime": "application/octet-stream"
    }
  ]
}
```

The client computes:

```txt
manifest_hash = sha256(canonical_manifest_json)
```

`manifest_hash` is stored in `JobStorage`.

### 7.3 Input root hash

`input_root_hash` commits to all input files declared by the manifest.

Simple version:

```txt
input_root_hash = sha256(input_hash_0 || input_hash_1 || ... || input_hash_n)
```

Recommended future version:

```txt
input_root_hash = Merkle root of all input hashes
```

A Merkle root makes it possible to prove membership of a single fragment input without downloading or revealing every input hash.

### 7.4 Storage reference hash

`storage_ref_hash` commits to a storage routing document.

Example storage reference document:

```json
{
  "protocol": "ipfs",
  "manifest_uri": "ipfs://Qm...",
  "mirrors": [
    "https://gateway.example/ipfs/Qm...",
    "https://storage.silicium.network/jobs/123/manifest.json"
  ],
  "manifest_sha256": "..."
}
```

Then:

```txt
storage_ref_hash = sha256(canonical_storage_reference_json)
```

Hashing the routing document is better than hashing only a URL because it can include multiple mirrors, content hashes and protocol metadata.

### 7.5 Encryption reference hash

`encryption_ref_hash` commits to encryption metadata when task files are encrypted.

Example:

```json
{
  "encryption": "aes-256-gcm",
  "key_policy": "worker_specific",
  "key_commitment": "...",
  "metadata_version": 1
}
```

If encryption metadata is not used:

```txt
encryption_ref_hash = [0u8; 32]
```

### 7.6 Worker storage checks

Before computing, a worker should:

```txt
1. fetch JobStorage from Solana
2. download the storage reference document from the scheduler/P2P layer
3. verify sha256(storage_reference_document) == storage_ref_hash
4. download the job manifest
5. verify sha256(manifest) == manifest_hash
6. find its fragment input inside the manifest
7. download the fragment input
8. verify sha256(input_file) == input_sha256 in the manifest
9. optionally verify the input is included in input_root_hash
10. compute the fragment
```

### 7.7 Verifier storage checks

Before voting, a verifier should:

```txt
1. fetch JobStorage
2. verify storage reference and manifest hashes
3. download the fragment input, output and proof
4. verify sha256(output_file) == fragment.result_hash
5. verify sha256(proof_manifest_or_artifact) == fragment.proof_ref
6. validate the computation or sampled proof
7. vote_fragment(true or false)
```

### 7.8 Hash formatting

All on-chain hash fields are `[u8; 32]`.

Recommended TypeScript helper:

```ts
import { createHash } from "crypto";

export function sha256Bytes(data: Buffer | Uint8Array | string): number[] {
  const bytes = typeof data === "string" ? Buffer.from(data) : Buffer.from(data);
  return Array.from(createHash("sha256").update(bytes).digest());
}
```

Do not hash only a URL when the goal is to prove file integrity. Hash the file content or a canonical manifest containing the file URI and content hash.

---

## 8. Reputation system

The program uses separate compute and verification reputation.

```txt
compute_reputation = trust as compute worker
verify_reputation  = trust as verifier
global_reputation  = derived general trust score
```

Initial state:

```txt
compute_reputation = 5000
verify_reputation  = 5000
global_reputation  = 5000
```

Bayesian memory starts with:

```txt
alpha = 5
beta  = 5
```

This represents a neutral prior.

### 8.1 Memory model

Compute memory:

```txt
compute_alpha_long / compute_beta_long
compute_alpha_short / compute_beta_short
```

Verifier memory:

```txt
verify_alpha_long / verify_beta_long
verify_alpha_short / verify_beta_short
```

Short-term memory reacts quickly to recent errors or fraud. Long-term memory changes more slowly and protects reliable participants from one isolated mistake.

### 8.2 Scoring weights

Compute score:

```txt
65% compute long memory
25% compute short memory
10% efficiency score
```

Verify score:

```txt
70% verify long memory
30% verify short memory
```

Global score:

```txt
50% compute reputation
50% verify reputation
```

### 8.3 Verifier-weighted penalties

When verifiers reject a compute result, the compute worker penalty is weighted by verifier trust:

```txt
low-trust verifier  -> smaller impact
high-trust verifier -> stronger impact
```

New verifiers still have a minimum impact so the network can bootstrap.

---

## 9. Instruction reference

### 9.1 `register_worker`

Creates a Worker account.

Effects:

- sets owner;
- initializes active stake fields empty;
- gives compute and verify roles by default;
- initializes compute, verify and global reputation at 5000;
- initializes Bayesian memory;
- emits `WorkerRegistered`.

### 9.2 `stake_worker(amount)`

Transfers SPL tokens into the worker stake vault.

Active stake is optional for bootstrap fragments and required for split and higher-risk fragments.

### 9.3 `create_job(...)`

Parameters:

```txt
job_id: u64
expected_fragments: u32
reward_per_fragment: u64
verifier_reward_per_vote: u64
verifier_reward_budget: u64
deadline_unix: i64
fragment_quorum: u16
```

Requirements:

```txt
expected_fragments > 0
expected_fragments <= MAX_FRAGMENTS_PER_JOB
reward_per_fragment > 0
2 <= fragment_quorum <= MAX_FRAGMENT_QUORUM
verifier_reward_budget >= expected_fragments * fragment_quorum * verifier_reward_per_vote
total deposit >= MIN_JOB_DEPOSIT
job TTL within min/max bounds
```

### 9.4 `declare_job_storage(...)`

Declares storage metadata for an open job.

Parameters:

```txt
manifest_hash: [u8; 32]
input_root_hash: [u8; 32]
storage_ref_hash: [u8; 32]
encryption_ref_hash: [u8; 32]
```

Requirements:

```txt
signer is job.client
job.status == Open
manifest_hash != zero
input_root_hash != zero
storage_ref_hash != zero
```

Effects:

```txt
creates JobStorage PDA
stores storage integrity commitments
emits JobStorageDeclared
```

`encryption_ref_hash` can be zero if no encryption metadata is declared.

### 9.5 `claim_fragment(fragment_index)`

Allows a compute worker to claim a leaf fragment.

Requirements:

```txt
worker has compute role
worker is active
worker.compute_reputation >= fragment.required_compute_reputation
worker.stake_amount >= fragment.required_stake
fragment is a leaf
fragment status is Available, Rejected, or expired Claimed
```

Because `MIN_COMPUTE_STAKE = 0`, bootstrap root fragments can be claimable without stake if `required_stake = 0`.

### 9.6 `submit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a 32-byte result hash and a 32-byte off-chain proof reference. The heavy result is not stored on-chain.

### 9.7 `resubmit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a new result after a result was rejected.

### 9.8 `reclaim_fragment(fragment_index)`

Releases an expired claim, decreases compute reputation for timeout, and makes the fragment available again.

### 9.9 `vote_fragment(choice)`

Verifier validation entrypoint.

```txt
choice = true  -> result valid
choice = false -> result invalid
```

Requirements:

```txt
verifier has verify role
verifier is active
verifier.verify_reputation >= MIN_VERIFY_REPUTATION
verifier is not the compute worker
verifier is not the job client
vote PDA prevents double vote
```

YES quorum:

```txt
fragment becomes Verified
worker paid
compute_reputation increases
verifier rewards become claimable
```

NO quorum:

```txt
fragment becomes Rejected
compute_reputation decreases with verifier-weighted penalty
verifier rewards become claimable for winning NO voters
```

### 9.10 `claim_verifier_reward`

Winning verifier claims their reward. `verify_reputation` increases after a correct winning reward claim.

### 9.11 `slash_vote`

Slashes a verifier who voted on the losing side after resolution.

Effects:

```txt
verify_reputation decreases
stake can be moved to treasury when available
vote is marked slashed
```

### 9.12 `propose_fragment_split(manifest_hash, child_count)`

A trusted compute worker proposes a split.

Requirements include:

```txt
compute role
active status
compute_reputation >= SPLIT_MIN_REPUTATION
stake_amount >= SPLIT_MIN_STAKE
parent is leaf
parent complexity >= SPLIT_MIN_COMPLEXITY
child_count > 1
child_count <= MAX_CHILDREN_PER_SPLIT
depth < DEFAULT_MAX_FRAGMENT_DEPTH
```

### 9.13 `approve_fragment_split`

Approves the split and moves the parent to `SplitApproved`.

### 9.14 `create_sub_fragment(...)`

Creates a child fragment.

Important parameters:

```txt
input_hash
required_compute_reputation
required_stake
complexity_score
```

### 9.15 `finalize_job(final_hash, output_uri)`

Finalizes a job after all expected leaf fragments are verified and all claimable verifier rewards are claimed.

### 9.16 `cancel_job`

Cancels an open job under program rules and refunds remaining escrow.

### 9.17 Passive staking instructions

```txt
init_staking_pool
stake_network
fund_staking_rewards
claim_staking_reward
request_unstake
withdraw_unstaked
```

---

## 10. Events

Program events:

```txt
JobCreated
JobStorageDeclared
WorkerRegistered
WorkerStaked
TreasuryInitialized
FragmentClaimed
FragmentReclaimed
FragmentSubmitted
FragmentVerified
FragmentRejected
VerifierRewardClaimed
JobFinalized
JobCancelled
VoteSlashed
DualReputationUpdated
BayesianReputationUpdated
FragmentSplitProposed
FragmentSplitApproved
FragmentSplitRejected
SubFragmentCreated
FragmentSplitCompleted
StakingPoolInitialized
NetworkStakeDeposited
StakingRewardsFunded
StakingRewardClaimed
NetworkUnstakeRequested
NetworkUnstakeWithdrawn
```

### `JobStorageDeclared`

```rust
pub struct JobStorageDeclared {
    pub job: Pubkey,
    pub job_storage: Pubkey,
    pub client: Pubkey,
    pub manifest_hash: [u8; 32],
    pub input_root_hash: [u8; 32],
    pub storage_ref_hash: [u8; 32],
    pub encryption_ref_hash: [u8; 32],
    pub created_at_unix: i64,
}
```

### `DualReputationUpdated`

```rust
pub struct DualReputationUpdated {
    pub worker: Pubkey,
    pub old_compute_reputation: i64,
    pub new_compute_reputation: i64,
    pub old_verify_reputation: i64,
    pub new_verify_reputation: i64,
    pub global_reputation: i64,
    pub reason: u8,
    pub status: u8,
}
```

### `BayesianReputationUpdated`

```rust
pub struct BayesianReputationUpdated {
    pub worker: Pubkey,
    pub reason: u8,
    pub compute_reputation: i64,
    pub verify_reputation: i64,
    pub global_reputation: i64,
    pub reliability_score: u32,
    pub compute_alpha_long: u64,
    pub compute_beta_long: u64,
    pub compute_alpha_short: u64,
    pub compute_beta_short: u64,
    pub verify_alpha_long: u64,
    pub verify_beta_long: u64,
    pub verify_alpha_short: u64,
    pub verify_beta_short: u64,
    pub compute_fraud_strikes: u16,
    pub verify_fraud_strikes: u16,
    pub fraud_strikes: u16,
    pub error_strikes: u16,
}
```

SDK event names use lower camel case:

```txt
jobStorageDeclared
dualReputationUpdated
bayesianReputationUpdated
```

---

## 11. State lifecycles

### 11.1 Job lifecycle

```txt
Open
 ├── Finalized
 └── Cancelled
```

### 11.2 Storage lifecycle

```txt
No JobStorage
   └── declare_job_storage
         └── JobStorage declared and immutable for the job
```

The storage declaration is intended to be a stable commitment to the task input set.

### 11.3 Leaf fragment lifecycle

```txt
Available
   └── Claimed
         ├── Submitted
         │     ├── Verified
         │     └── Rejected
         │           └── resubmit_fragment_result
         └── Available again through reclaim_fragment if expired
```

### 11.4 Split lifecycle

```txt
Claimed / Available leaf
   └── SplitPending
         └── SplitApproved
               ├── child fragments created as Available leaves
               └── SplitParent after all children exist
```

### 11.5 Passive staker lifecycle

```txt
No account
   └── stake_network
         └── Active stake
               ├── claim_staking_reward
               └── request_unstake
                     └── cooldown
                           └── withdraw_unstaked
```

---

## 12. Security invariants

### 12.1 Compute access

A worker can compute only if:

```txt
worker active
ROLE_COMPUTE set
compute_reputation high enough
stake_amount >= fragment.required_stake
active_claims < MAX_ACTIVE_CLAIMS_PER_WORKER
fragment is a leaf
```

### 12.2 Verify access

A verifier can vote only if:

```txt
worker active
ROLE_VERIFY set
verify_reputation high enough
not the job client
not the submitting worker
not already voted in that round
```

### 12.3 Storage integrity

Workers and verifiers must verify downloaded data before using it:

```txt
sha256(storage reference) == storage_ref_hash
sha256(job manifest) == manifest_hash
input checksums match manifest
result output hash matches result_hash
proof/reference hash matches proof_ref
```

### 12.4 Bootstrap safety

Bootstrap fragments can require zero stake. Safety comes from:

```txt
reputation-gated task allocation
high verification probability for new/low-reputation participants
low-risk tasks for new participants
low rewards for low-trust tasks
active claim limits
short claim TTL / reclaim mechanism
```

### 12.5 Split safety

Split remains stake-protected and reputation-protected:

```txt
SPLIT_MIN_REPUTATION
SPLIT_MIN_STAKE
SPLIT_MIN_COMPLEXITY
MAX_CHILDREN_PER_SPLIT
DEFAULT_MAX_FRAGMENT_DEPTH
```

### 12.6 Payment safety

A worker can only be paid when:

```txt
fragment submitted
YES quorum reached
fragment transitions to Verified
escrow contains enough tokens
worker_token.owner == fragment.worker
worker_token.mint == job.mint
```

### 12.7 Verifier reward safety

A verifier reward can only be claimed when:

```txt
round is resolved
vote is on winning side
vote not already claimed
eligible reward limit not exceeded
```

### 12.8 Finalization reward lock

A job cannot be finalized while claimable verifier rewards remain unclaimed.

### 12.9 Passive staking accounting

Passive staking uses accumulated reward-per-share accounting, avoiding loops over all stakers.

---

## 13. SDK integration

The SDK should expose:

```ts
sdk.declareJobStorage(params)
sdk.fetchJobStorage(job)
sdk.pdas.jobStorage(job)
```

Example:

```ts
await sdk.declareJobStorage({
  job,
  manifestHash,
  inputRootHash,
  storageRefHash,
  encryptionRefHash, // optional, defaults to zero hash if supported by SDK wrapper
});

const storage = await sdk.fetchJobStorage(job);
```

The SDK should also use:

```ts
worker.computeReputation
worker.verifyReputation
worker.globalReputation
```

For sub-fragments, SDK params should use:

```ts
requiredComputeReputation
```

SDK event list should include:

```txt
jobStorageDeclared
dualReputationUpdated
bayesianReputationUpdated
```

### 13.1 Worker node storage logic

Worker node pseudocode:

```ts
const storage = await sdk.fetchJobStorage(job);

const storageRef = await p2p.downloadStorageRef(job);
assert(sha256(storageRef) === storage.storageRefHash);

const manifest = await p2p.downloadManifest(storageRef);
assert(sha256(manifest) === storage.manifestHash);

const input = await p2p.downloadFragmentInput(manifest, fragmentIndex);
assert(sha256(input) === manifest.fragments[fragmentIndex].input_sha256);

const output = await compute(input);
const resultHash = sha256(output);

const proofManifest = await p2p.uploadProofAndBuildManifest(output);
const proofRef = sha256(proofManifest);

await sdk.submitFragmentResult({ job, fragmentIndex, resultHash, proofRef, workerToken });
```

### 13.2 Verifier node storage logic

Verifier node pseudocode:

```ts
const storage = await sdk.fetchJobStorage(job);
const manifest = await loadAndVerifyManifest(storage);
const output = await p2p.downloadOutput(fragment.proofRef);
assert(sha256(output) === fragment.resultHash);

const isValid = await verifyComputation(manifest, fragment, output);
await sdk.voteFragment({ job, fragment, choice: isValid });
```

---

## 14. Backend / indexer model

The backend should listen to events and maintain a database projection.

Recommended tables:

### `jobs`

| Column | Source |
|---|---|
| `job_pubkey` | `JobCreated.job` |
| `client` | `JobCreated.client` |
| `mint` | `JobCreated.mint` |
| `expected_fragments` | `JobCreated`, `FragmentSplitCompleted` |
| `verified_fragments` | `FragmentVerified` |
| `status` | `JobCreated`, `JobFinalized`, `JobCancelled` |
| `deadline_unix` | `JobCreated.deadline_unix` |

### `job_storage`

| Column | Source |
|---|---|
| `job_pubkey` | `JobStorageDeclared.job` |
| `job_storage_pubkey` | `JobStorageDeclared.job_storage` |
| `client` | `JobStorageDeclared.client` |
| `manifest_hash` | `JobStorageDeclared.manifest_hash` |
| `input_root_hash` | `JobStorageDeclared.input_root_hash` |
| `storage_ref_hash` | `JobStorageDeclared.storage_ref_hash` |
| `encryption_ref_hash` | `JobStorageDeclared.encryption_ref_hash` |
| `created_at_unix` | `JobStorageDeclared.created_at_unix` |

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
| `parent_fragment` | `SubFragmentCreated`, account fetch |
| `depth` | `SubFragmentCreated`, account fetch |
| `is_leaf` | account fetch |
| `complexity_score` | `SubFragmentCreated`, account fetch |
| `split_manifest_hash` | `FragmentSplitApproved`, account fetch |

### `workers`

| Column | Source |
|---|---|
| `worker` | `WorkerRegistered.worker` |
| `worker_account` | `WorkerRegistered.worker_account` |
| `roles` | `WorkerRegistered.roles` |
| `status` | `WorkerRegistered`, account fetch |
| `stake_amount` | `WorkerStaked`, account fetch after slash |
| `compute_reputation` | `DualReputationUpdated`, `BayesianReputationUpdated`, account fetch |
| `verify_reputation` | `DualReputationUpdated`, `BayesianReputationUpdated`, account fetch |
| `global_reputation` | `DualReputationUpdated`, `BayesianReputationUpdated`, account fetch |
| `reliability_score` | `BayesianReputationUpdated`, account fetch |
| `active_claims` | account fetch after claim, submit, reclaim |

### `votes`

| Column | Source |
|---|---|
| `fragment` | vote account / fragment events |
| `verifier` | vote account / reward events |
| `round` | vote account |
| `choice` | fetched from `FragmentVote` |
| `reward_claimed` | `VerifierRewardClaimed` |
| `slashed` | `VoteSlashed` |

---

## 15. Test suite status

Validated tests include:

```txt
initial compute/verify/global reputation at 5000
compute success increases compute only
compute rejection decreases compute only
verifier reward increases verify only
verifier reward does not improve compute
expired claim penalizes compute only
slash wrong vote decreases verify only
higher verify reputation causes stronger compute penalty
sub-fragment rejection cases
split parent cannot be claimed
mixed leaf finalization
bootstrap claim without active stake
bootstrap vote without active stake
job creation anti-spam
quorum 2 validation
passive staking
slash double-vote protection
job storage declaration
invalid zero storage hash rejection
non-client storage declaration rejection
```

Run:

```bash
anchor test --provider.cluster localnet
```

---

## 16. Devnet workflow

Build:

```bash
anchor build
```

Check ID:

```bash
solana address -k target/deploy/solana_layer-keypair.json
grep -R "declare_id" programs/solana-layer/src/lib.rs
grep -n "solana_layer" Anchor.toml
```

Deploy:

```bash
solana program deploy target/deploy/solana_layer.so \
  --url https://api.devnet.solana.com \
  --program-id target/deploy/solana_layer-keypair.json \
  --max-sign-attempts 100 \
  --with-compute-unit-price 10000
```

Check:

```bash
solana program show 48Bdt8Dg9FW8n6Mpvvdh6dgTXrsBvBfqMrwhnWQ2WQm1 --url devnet
```

Run smoke tests:

```bash
npx ts-node scripts/devnet_smoke_test.ts
npx ts-node scripts/devnet_smoke_test.ts --write
npx ts-node scripts/devnet_minimal_job_flow.ts
```

If deployment fails and creates a buffer:

```bash
solana program show --buffers --url devnet
solana program close BUFFER_ADDRESS --url devnet
```

---

## 17. CI workflow notes

The CI must use the same Anchor CLI version as `anchor-lang`.

Recommended `Anchor.toml` toolchain:

```toml
[toolchain]
anchor_version = "0.32.1"
package_manager = "yarn"
```

Recommended CI sync:

```bash
anchor keys sync --provider.cluster localnet
anchor build --provider.cluster localnet
anchor test --provider.cluster localnet
```

Do not cache `target/deploy/solana_layer-keypair.json` across CI runs unless program IDs are intentionally fixed, because stale keypairs can cause `DeclaredProgramIdMismatch`.

Generated test workers must have SOL before calling `registerWorker`, because `registerWorker` creates the worker PDA using the worker signer as payer.

---

## 18. Milestones roadmap

Current validation uses:

```txt
result_hash
proof_ref
vote_fragment(choice)
```

A milestone workflow can add:

```txt
milestone_root
milestone_count
challenge_seed
submit_milestone_check or validate_fragment
```

The purpose is probabilistic verification: workers commit to intermediate states, and verifiers check a random sample after submission.

Milestones should connect naturally to the storage system:

```txt
milestone_root stored on-chain
milestone proofs stored off-chain
milestone sample proofs downloaded by verifiers
checksums verified against milestone_root
```

---

## 19. Production readiness notes

Before beta/mainnet:

- raise split thresholds;
- tune bootstrap task limits;
- add an indexer for all Anchor events;
- implement durable P2P/off-chain storage for manifests, inputs, outputs and proofs;
- define canonical JSON serialization for all manifests;
- audit storage hash validation and SDK hash helpers;
- audit slashing and weighted reputation logic;
- increase unstake cooldown;
- increase claim TTLs for real compute workloads;
- add challenge windows for final results;
- add role/tier policies in the scheduler;
- define encryption/key distribution rules for private tasks;
- keep passive staking non-slashable unless delegation is introduced.

---

## 20. Conceptual model

The current design separates five concepts:

```txt
Storage    = off-chain task data and proofs
Hashes     = integrity commitments on-chain
Reputation = historical trust
Stake      = economic risk for valuable work
Scheduler  = off-chain assignment and market logic
```

New participants begin with neutral trust, receive low-risk work, are heavily verified, and move up naturally if they perform well.

Trusted participants receive more valuable work, less redundant verification, and better economics.

The storage layer gives workers and verifiers a standard way to download task data and verify checksums without putting heavy files on Solana.

