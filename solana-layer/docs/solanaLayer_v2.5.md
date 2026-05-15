# Technical Documentation — Silicium Solana Layer

Project: **Silicium / EIP**  
Anchor program: `solana-layer`  
Current Devnet Program ID:

```txt
48Bdt8Dg9FW8n6Mpvvdh6dgTXrsBvBfqMrwhnWQ2WQm1
```

Keep `declare_id!(...)`, `Anchor.toml`, `target/deploy/solana_layer-keypair.json`, SDK constants, smoke tests and dashboard configuration aligned with this Program ID.

---

## 1. Purpose of the Solana Layer

The Solana Layer is the on-chain settlement, validation, staking, reputation, reward and slashing layer of Silicium.

It does **not** execute heavy computation directly. Computation, rendering, simulation, AI inference and scientific processing happen off-chain. The on-chain program manages:

- job creation and escrow funding;
- fragment and sub-fragment lifecycle;
- worker and verifier registration;
- optional active stake for higher-risk work;
- role-specific reputation;
- result hash submission;
- verifier voting;
- worker payments;
- verifier rewards;
- vote slashing;
- passive network staking;
- job finalization and cancellation.

---

## 2. High-level architecture

### Normal compute flow

```txt
Client
  └── create_job
        └── escrow funded
              └── worker claim_fragment
                    └── worker computes off-chain
                          └── submit_fragment_result(result_hash, proof_ref)
                                └── verifiers vote_fragment
                                      ├── YES quorum => fragment verified + worker paid + compute reputation increases
                                      └── NO quorum  => fragment rejected + compute reputation decreases
```

### Split / sub-fragment flow

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

### Passive staking flow

```txt
init_staking_pool
  └── stake_network
        └── fund_staking_rewards
              └── claim_staking_reward
                    └── request_unstake
                          └── cooldown
                                └── withdraw_unstaked
```

---

## 3. Actors

### Client

Creates and funds jobs. The client can finalize or cancel jobs according to program rules. The client cannot verify their own job.

### Compute worker

Computes fragments off-chain. Access is controlled by:

```txt
ROLE_COMPUTE
compute_reputation
active_claims
fragment.required_compute_reputation
fragment.required_stake
```

### Verifier

Verifies submitted results and votes. Access is controlled by:

```txt
ROLE_VERIFY
verify_reputation
not the submitting worker
not the job client
```

### Slasher

Any signer can slash an incorrect verifier vote after a round resolution.

### Passive network staker

Stakes tokens in the network-level staking pool. Passive stakers are separate from active workers/verifiers and do not need a Worker account.

### Split approver / scheduler

Approves or rejects split proposals. In the current architecture this is scheduler/backend-governed. Later policies can use verifier quorum or governance.

---

## 4. Constants

Important constants:

| Constant | Meaning | Value / note |
|---|---|---:|
| `MIN_COMPUTE_STAKE` | Minimum active stake for normal compute bootstrap | `0` |
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

### Split constants

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

### 5.1 `Worker`

The `Worker` account stores identity, roles, active stake, reputation, counters and scheduler-oriented scores.

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

PDA:

```txt
[b"worker", owner]
```

Roles:

```txt
ROLE_COMPUTE = 1
ROLE_VERIFY  = 2
```

Optional scheduler role preference:

```txt
ROLE_AUTO = 0
ROLE_COMPUTE_PREFERRED = 1
ROLE_VERIFY_PREFERRED = 2
```

### 5.2 `Job`

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
| `deadline_unix` | Job deadline |
| `fragment_quorum` | Required votes per fragment |
| `status` | Open / Finalized / Cancelled |

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

### 5.5 Other accounts

#### `FragmentVote`

PDA:

```txt
[b"fragment_vote", fragment, verifier, round_le_u16]
```

Stores one vote per verifier per fragment round.

#### `FragmentResolution`

PDA:

```txt
[b"fragment_resolution", fragment, round_le_u16]
```

Stores final winning side and eligible verifier reward count.

#### `JobResult`

PDA:

```txt
[b"result", job]
```

Stores final hash and output URI.

#### `Treasury`

Receives slashed stake.

#### `StakingPool` and `NetworkStaker`

Used for passive network staking and reward distribution.

---

## 6. Reputation system

The program uses separate compute and verification reputation.

```txt
compute_reputation = trust as compute worker
verify_reputation  = trust as verifier
global_reputation  = derived general trust score
```

### Initial state

Registered participants start neutral:

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

This represents a 50% neutral prior.

### Memory model

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

### Scoring weights

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

### Verifier weighted penalties

When a verifier contributes to rejecting a compute result, the compute worker penalty is weighted by that verifier's `verify_reputation`.

```txt
low-trust verifier  -> smaller impact
high-trust verifier -> stronger impact
```

New verifiers still have a minimum impact so the network can bootstrap.

---

## 7. Instruction reference

### `register_worker`

Creates a Worker account.

Effects:

- sets owner;
- initializes active stake fields empty;
- gives compute and verify roles by default;
- initializes reputation at 5000 / 5000 / 5000;
- initializes Bayesian memory;
- emits `WorkerRegistered`.

### `stake_worker(amount)`

Transfers SPL tokens into the worker stake vault. This is optional for bootstrap fragments and required for split and future high-risk fragments.

### `create_job(...)`

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

### `claim_fragment(fragment_index)`

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

### `submit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a 32-byte result hash and a 32-byte off-chain proof reference. The heavy result is not stored on-chain.

### `resubmit_fragment_result(fragment_index, result_hash, proof_ref)`

Submits a new result after a result was rejected.

### `reclaim_fragment(fragment_index)`

Releases an expired claim, decreases compute reputation for timeout, and makes the fragment available again.

### `vote_fragment(choice)`

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

### `claim_verifier_reward`

Winning verifier claims their reward. `verify_reputation` increases after a correct winning reward claim.

### `slash_vote`

Slashes a verifier who voted on the losing side after resolution.

Effects:

```txt
verify_reputation decreases
verify_fraud_strikes / verify_failures can increase depending on logic
stake can be moved to treasury when available
```

### `propose_fragment_split(manifest_hash, child_count)`

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

### `approve_fragment_split`

Approves the split and moves the parent to `SplitApproved`.

### `create_sub_fragment(...)`

Creates a child fragment.

Important parameters:

```txt
required_compute_reputation
required_stake
complexity_score
input_hash
```

### `finalize_job(final_hash, output_uri)`

Finalizes a job after all expected leaf fragments are verified and all claimable verifier rewards are claimed.

### `cancel_job`

Cancels an open job under program rules and refunds remaining escrow.

### Passive staking instructions

```txt
init_staking_pool
stake_network
fund_staking_rewards
claim_staking_reward
request_unstake
withdraw_unstaked
```

Passive staking is separate from active worker/verifier behavior.

---

## 8. Events

Program events:

```txt
JobCreated
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

SDK names use lower camel case:

```txt
dualReputationUpdated
bayesianReputationUpdated
```

---

## 9. State lifecycles

### Job lifecycle

```txt
Open
 ├── Finalized
 └── Cancelled
```

### Leaf fragment lifecycle

```txt
Available
   └── Claimed
         ├── Submitted
         │     ├── Verified
         │     └── Rejected
         │           └── resubmit_fragment_result
         └── Available again through reclaim_fragment if expired
```

### Split lifecycle

```txt
Claimed / Available leaf
   └── SplitPending
         └── SplitApproved
               ├── child fragments created as Available leaves
               └── SplitParent after all children exist
```

### Passive staker lifecycle

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

## 10. Security invariants

### Compute access

A worker can compute only if:

```txt
worker active
ROLE_COMPUTE set
compute_reputation high enough
stake_amount >= fragment.required_stake
active_claims < MAX_ACTIVE_CLAIMS_PER_WORKER
fragment is a leaf
```

### Verify access

A verifier can vote only if:

```txt
worker active
ROLE_VERIFY set
verify_reputation high enough
not the job client
not the submitting worker
not already voted in that round
```

### Bootstrap safety

Bootstrap fragments can require zero stake. Safety comes from:

```txt
reputation-gated task allocation
high verification probability for new/low-reputation participants
low-risk tasks for new participants
low rewards for low-trust tasks
active claim limits
short claim TTL / reclaim mechanism
```

### Split safety

Split remains stake-protected and reputation-protected:

```txt
SPLIT_MIN_REPUTATION
SPLIT_MIN_STAKE
SPLIT_MIN_COMPLEXITY
MAX_CHILDREN_PER_SPLIT
DEFAULT_MAX_FRAGMENT_DEPTH
```

### Result storage

The on-chain program stores:

```txt
result_hash
proof_ref
final_hash
output_uri
```

It does not store large outputs. Heavy data belongs in IPFS, Arweave, S3, backend storage or another durable off-chain layer.

---

## 11. Hash handling

Hashes are integrity commitments between the off-chain compute layer and the on-chain settlement layer.

```txt
on-chain  = hash + state + payments + votes
off-chain = files + inputs + outputs + proofs
```

Recommended pattern:

```txt
input file or manifest -> input_hash
worker output          -> result_hash
proof manifest         -> proof_ref
final assembled output -> final_hash
```

Hash file content, not only URLs. If a URI is needed, use a canonical manifest:

```json
{
  "uri": "ipfs://...",
  "content_hash": "sha256_hex_of_file",
  "size": 123456,
  "mime": "image/png"
}
```

Then hash the canonical manifest if a 32-byte `proof_ref` is needed.

---

## 12. Test suite status

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
```

Run:

```bash
anchor test --provider.cluster localnet
```

---

## 13. SDK integration

The SDK should use:

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
dualReputationUpdated
bayesianReputationUpdated
```

---

## 14. Devnet workflow

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
solana program deploy target/deploy/solana_layer.so   --url https://api.devnet.solana.com   --program-id target/deploy/solana_layer-keypair.json   --max-sign-attempts 100   --with-compute-unit-price 10000
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

## 15. Milestones roadmap

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

---

## 16. Production readiness notes

Before beta/mainnet:

- raise split thresholds;
- tune bootstrap task limits;
- add an indexer for all Anchor events;
- use durable off-chain storage for job inputs/results/proofs;
- audit slashing and weighted reputation logic;
- increase unstake cooldown;
- increase claim TTLs for real compute workloads;
- add challenge windows for final results;
- add role/tier policies in the scheduler;
- keep passive staking non-slashable unless delegation is introduced.

---

## 17. Conceptual model

The current design separates three concepts:

```txt
Reputation = historical trust
Stake      = economic risk for valuable work
Scheduler  = off-chain assignment and market logic
```

New participants begin with neutral trust, receive low-risk work, are heavily verified, and move up naturally if they perform well.

Trusted participants receive more valuable work, less redundant verification, and better economics.

This supports the Silicium goal: a distributed compute network where the best machines naturally rise toward the roles where they are most useful.

