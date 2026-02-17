# Silicium Chain – On-chain Job & Reward Layer

Silicium Chain is the **on-chain layer** of the Silicium project.  
It is responsible for **coordination, fund security, and decentralized rewards distribution** for distributed computation executed off-chain by the network.

Computation, task splitting, and execution are **off-chain**.  
The blockchain acts as a **source of truth, escrow, and decentralized validation layer**.

---

## Purpose of the Layer

This Solana program (built with Anchor) enables:

- Registration of **distributed computation jobs**
- Securing client funds via a **SPL Token escrow**
- Management of **computation fragments**
- **Per-fragment rewards** for workers
- **Decentralized fragment validation (quorum-based)**
- **Stake slashing** for incorrect votes (economic security)
- A **Treasury** to collect slashed stake
- Secure job **finalization or cancellation**

This layer is fully functional and ready to be deployed on **devnet**.

---

# State Model

## Job

Represents a global computation task submitted by a client.

### Main fields

- `job_id`: logical job identifier  
- `client`: job creator  
- `mint`: SPL token used for rewards  
- `escrow`: SPL token escrow account  
- `expected_fragments`: total number of fragments  
- `verified_fragments`: number of verified fragments  
- `reward_per_fragment`: reward per fragment  
- `deposited_amount`: total deposited funds  
- `paid_amount`: total distributed rewards  
- `deadline_unix`: job deadline  
- `status`: `Open | Cancelled | Finalized`  
- `fragment_quorum`: required number of YES votes per fragment  
- `verified_at_unix`: timestamp when all fragments reached quorum  

### Important Change

Silicium Chain is now **fully decentralized**:

- ❌ No `verifier_authority`
- ❌ No `challenge_window`
- ✅ Validation is purely quorum-based

---

## Fragment

Represents **one unique fragment** of a job  
(1 `fragment_index` = 1 on-chain fragment account).

### Key guarantees

- Only one fragment per `(job, fragment_index)`
- A fragment cannot be verified more than once
- Voting and payment are strictly controlled on-chain
- A rejected fragment can be **resubmitted** in a new **round**

### Main fields

- `job`
- `fragment_index`
- `worker`
- `result_hash`
- `proof_ref`
- `status`: `Submitted | Verified | Rejected`
- `yes_votes`
- `no_votes`
- `required_quorum`
- `voting_deadline_unix`
- `round` (increments when resubmitted)

`required_quorum` is initialized from `job.fragment_quorum` when the fragment is first submitted.

---

## Worker

Represents a registered participant in the network  
(worker and/or verifier).

Workers must be **explicitly registered on-chain** and may lock tokens as stake to participate in fragment verification.

### Main fields

- `owner`: worker authority (signer)
- `roles`: bitflags defining worker capabilities
- `stake_mint`: SPL token used for staking
- `stake_vault`: escrow account holding staked tokens
- `stake_amount`: total amount staked
- `reputation`: reputation score (future use)
- `status`: `Active | Banned`
- `total_submitted`
- `total_verified`
- `total_rejected`

---

## Worker Roles

Each worker has explicit on-chain roles:

- `ROLE_COMPUTE`: may submit fragment results
- `ROLE_VERIFY`: may participate in fragment voting

A worker may hold multiple roles.  
Roles are enforced at instruction level.

---

## FragmentVote

Prevents double voting and stores a verifier decision.

- One `FragmentVote` PDA per `(fragment, verifier, round)`
- Ensures strict **one vote per verifier per round**
- Stores:
  - `choice`: YES/NO
  - `round`: current round of the fragment
  - `slashed`: prevents double slashing for this vote

---

## Treasury

Collects slashed stake and centralizes economic penalties into an auditable pool.

### Why it exists

Without a treasury, slashed stake would have no deterministic destination (burning is possible, but not always desired).  
With a treasury, the protocol can later decide how to use penalties:

- fund verifiers / security incentives
- reward honest participants
- finance protocol operations (governance later)
- potentially burn partially (future policy)

### On-chain structure

Two pieces:

1) **Treasury state (`Treasury`)**: stores metadata  
- `mint`: token mint used by the treasury  
- `authority`: PDA that owns the treasury token account  
- `admin`: optional admin key (future governance / withdrawals)  
- `bump`: PDA bump  

2) **Treasury token account (`TokenAccount`)**: holds slashed tokens  
- `owner = treasury_authority PDA`
- `mint = job.mint`

---

## JobResult

Stores the final result of a completed job.

- `final_hash`: hash of the final computation result
- `uri_bytes`: bounded-size URI pointing to off-chain data

---

# Escrow & Fund Security

- Client funds are deposited into a **SPL Token escrow**
- Escrow is controlled by a **Program Derived Address (PDA)**
- Workers are paid **on-chain** upon quorum
- Remaining funds are automatically **refunded** to the client upon finalization or cancellation

All financial flows are fully deterministic and auditable.

---

# Decentralized Verification Model

Fragment validation is now **fully quorum-based**.

## Voting Rules

A verifier must:

- Be a registered `Worker`
- Be `Active`
- Have `ROLE_VERIFY`
- Have a minimum stake (`MIN_VERIFIER_STAKE`)
- Not vote on their own fragment

A fragment becomes:

- `Verified` when `yes_votes >= required_quorum`
- `Rejected` when `no_votes >= required_quorum`

Payment is executed **exactly once**, when quorum is reached.

---

## Quorum Model

Each job defines: `fragment_quorum`

This value determines how many YES votes are required for a fragment to be validated.

This allows:

- Flexible security levels per job
- Adaptation to network size
- Progressive decentralization

Example (majority model):  
`fragment_quorum = total_verifiers / 2 + 1`

---


# Resubmission Rounds

When a fragment is rejected:

- The fragment can be resubmitted via `resubmit_fragment_result`
- `round` increments
- votes reset (`yes_votes = 0`, `no_votes = 0`)
- new compute worker can take over
- new votes are recorded under new vote PDAs `(fragment, verifier, round)`

This prevents vote collisions and keeps history slashable per round.

---

# Slashing Model (Economic Security)

Silicium Chain includes **vote slashing** to penalize incorrect verification votes once a fragment is resolved.

## What gets slashed?

When a fragment is resolved:

- If fragment is `Verified`, then **NO votes are wrong**
- If fragment is `Rejected`, then **YES votes are wrong**

A wrong vote can be slashed **once**.

## How much is slashed?

Current policy (configurable):

- `SLASH_BPS = 1000` (10%)
- `slash_amount = max(1, stake_amount * 10%)`
- Clamped to vault balance

## Where does slashed stake go?

- Slashed tokens are transferred from the verifier `stake_vault`
- Into the **Treasury token account** (owned by treasury PDA)

## Why “permissionless”?

`slash_vote` can be called by **anyone** (a “slasher”):

- makes slashing enforceable even without a central actor
- incentivizes future “watchers” / bots to execute it

---

# Implemented Instructions

## `create_job`

- Initializes the `Job`
- Creates the escrow account
- Transfers total required funds
- Stores `fragment_quorum`

---

## `submit_fragment_result`

Allows a worker to submit a fragment result.

Rules:

- Worker must be `Active`
- Must have `ROLE_COMPUTE`
- Fragment is uniquely identified
- Verified fragments cannot be overwritten
- `required_quorum` is initialized from `job.fragment_quorum`

---

## `resubmit_fragment_result`
Only when fragment is `Rejected`:
- increments `round`
- resets votes
- updates worker + worker_token_account + new hashes
- sets status back to `Submitted`

---
## `vote_fragment`

Fully decentralized validation.

Rules:

- Must be `ROLE_VERIFY`
- Must be staked
- Cannot self-vote
- One vote per verifier (PDA enforced)
- Quorum determines final status
- Payment executed atomically upon quorum

---

## `init_treasury`

Initializes the treasury for a given `mint`:

- Creates `Treasury` state PDA
- Creates the treasury token account (owned by treasury authority PDA)

This must be done once per reward/stake mint.

---

## `slash_vote`

Slashes a wrong-side vote after fragment resolution:

- Requires fragment not `Submitted`
- Requires `FragmentVote.slashed == false`
- Transfers a fraction of stake from `stake_vault` → `treasury`
- Marks `FragmentVote.slashed = true`
- Decreases `Worker.stake_amount`

---

## `finalize_job`

Can be executed when: `verified_fragments == expected_fragments`

Actions:

- Stores `JobResult`
- Refunds remaining escrow
- Closes escrow
- Sets status to `Finalized`

There is no challenge window anymore.

---

## `cancel_job`

Cancels a job if:

- No fragment has been paid OR
- Deadline has passed

Actions:

- Refunds remaining funds
- Closes escrow
- Sets status to `Cancelled`

---

## `register_worker`

Creates a worker account.

Required before:

- Submitting fragments
- Voting on fragments

---

# Architectural Choices

- Off-chain computation
- On-chain coordination
- Stake-based decentralized validation
- Deterministic quorum model
- Atomic reward execution
- Permissionless slashing
- Treasury-based penalty collection
- Fully auditable financial logic

---

# Current Limitations

- Treasury withdrawals policy not implemented yet (admin/governance later)
- No weighted voting yet
- No dynamic on-chain verifier counting
- No unstake cooldown
- No automatic fragment assignment

---

# Status

- Centralized verification removed
- Full quorum-based validation implemented
- Escrow model stable
- Slashing implemented
- Treasury implemented
- Security checks enforced
- Ready for **devnet deployment**
- Designed for progressive decentralization

---

# Summary

Silicium Chain is now a:

**Fully decentralized coordination, payment, and security layer**  
for distributed computation.

It is:

- minimal  
- secure  
- deterministic  
- extensible  
- quorum-based  
- economically aligned  

It provides the secure on-chain foundation of Silicium.
