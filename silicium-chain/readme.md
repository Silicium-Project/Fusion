# Silicium Chain – On-chain Job & Reward Layer

Silicium Chain is the **on-chain layer** of the Silicium project.  
It is responsible for **coordination, fund security, and rewards distribution** for distributed computation executed off-chain by the network.

Computation, task splitting, and execution are **off-chain**.  
The blockchain acts as a **source of truth, escrow, and verifiable payment layer**.

---

## Purpose of the Layer

This Solana program (built with Anchor) enables:

- Registration of **distributed computation jobs**
- Securing client funds via a **SPL Token escrow**
- Management of **computation fragments**
- **Per-fragment rewards** for workers
- Verification of fragment results
- Secure job **finalization or cancellation**

This layer is **functional**, ready to be deployed on **devnet**.

---

## State Model

### Job
Represents a global computation task submitted by a client.

Main fields:
- `job_id`: logical job identifier
- `client`: job creator
- `mint`: SPL token used for rewards
- `escrow`: SPL token escrow account
- `expected_fragments`: total number of fragments
- `verified_fragments`: number of verified fragments
- `reward_per_fragment`: reward per fragment
- `deadline_unix`: job deadline
- `status`: `Open | Cancelled | Finalized`
- `verifier_authority`: verification authority (MVP = client)
- `challenge_window_sec`: challenge window (MVP = 0)

---

### Fragment
Represents **one unique fragment** of a job  
(1 `fragment_index` = 1 on-chain fragment account).

Key guarantees:
- Only one fragment per `(job, fragment_index)`
- A fragment cannot be verified more than once

Main fields:
- `job`
- `fragment_index`
- `worker`
- `result_hash`
- `proof_ref`
- `status`: `Submitted | Verified | Rejected`

---

### Worker
Represents a registered participant in the network  
(worker and/or verifier).

Workers must be **explicitly registered on-chain** and may lock
tokens as stake to participate in fragment verification.

Main fields:
- `owner`: worker authority (signer)
- `stake_mint`: SPL token used for staking
- `stake_vault`: escrow account holding staked tokens
- `stake_amount`: total amount staked
- `reputation`: reputation score (future use)
- `status`: `Active | Banned`
- `total_submitted`: number of fragments submitted
- `total_verified`: number of fragments verified
- `total_rejected`: number of fragments rejected

---

### JobResult
Stores the final result of a completed job.

- `final_hash`: hash of the final computation result
- `uri_bytes`: bounded-size URI pointing to off-chain data

---

## Escrow & Fund Security

- Client funds are deposited into a **SPL Token escrow**
- The escrow is controlled by a **Program Derived Address (PDA)**
- Workers are paid **on-chain**, fragment by fragment
- Remaining funds are automatically **refunded** to the client upon finalization or cancellation

---

## Worker Stake & Verifier Security

To participate in fragment verification, a worker must lock
tokens as **stake** on-chain.

- Stake is deposited into a **worker-specific escrow (PDA)**
- Only **staked and active workers** may act as verifiers
- Stake creates an economic cost for malicious behavior
- The staking model enables future **slashing and weighted voting**

Minimum verifier stake (To change):
- `MIN_VERIFIER_STAKE = 1` token

---

## Implemented Instructions

### `create_job`
Creates a job and:
- Initializes the `Job` account
- Creates the SPL escrow account
- Deposits the required funds  
  (`expected_fragments × reward_per_fragment`)

---

### `submit_fragment_result`
Allows a worker to submit a result for a specific fragment.

Rules:
- Fragments are uniquely identified by `(job, fragment_index)`
- A verified fragment cannot be overwritten
- A rejected fragment may be resubmitted

---

### `verify_fragment`
Verifies a submitted fragment.

- Verification authority: `verifier_authority` (MVP = client)
- If accepted:
  - The worker is paid immediately
  - Fragment status becomes `Verified`
- If rejected:
  - Fragment status becomes `Rejected`

---

### `finalize_job`
Finalizes a job **only when all fragments are verified**.

Actions:
- Stores the `JobResult`
- Refunds remaining escrow funds
- Closes the escrow account
- Sets the job status to `Finalized`

Optional:
- Supports a `challenge_window`  
  (currently set to `0` for the MVP)

---

### `cancel_job`
Cancels a job if:
- No fragment has been paid **or**
- The job deadline has passed

Actions:
- Refunds remaining funds
- Closes the escrow
- Sets the job status to `Cancelled`

---

### `register_worker`
Registers a worker in the network.

Actions:
- Creates a `Worker` account (PDA)
- Initializes worker metadata
- Marks the worker as `Active`

Required before:
- Submitting fragments
- Verifying fragments

---

### `vote_fragment`
Decentralized verification (quorum-based).

- Any verifier must be a registered `Worker`
- Must be `Active`
- Must have a minimum stake: `MIN_VERIFIER_STAKE`
- A fragment becomes `Verified` when quorum is reached
- Payment is executed once upon quorum
- A `FragmentVote` PDA prevents double voting

---

## Architectural Choices

- **Off-chain computation**, on-chain coordination
- Explicit, auditable fragment tracking
- Immediate per-fragment payments
- No implicit trust between participants
- All financial flows are **fully auditable on-chain**

---

## Current Limitations

- Two verification flows exist:
  - `verify_fragment`: centralized (MVP)
  - `vote_fragment`: decentralized quorum voting (in progress / optional)

This logic **does not yet include**:
- No slashing yet (stake is locked but cannot be penalized)
- No unstake / cooldown yet
- No automatic fragment assignment

---

## Status

- Core logic fully implemented
- Basic security guarantees in place
- Ready for **devnet deployment**
- Designed for progressive decentralization

---

## Summary

Silicium Chain is a **coordination and payment layer** for distributed computation, designed to be:
- minimal
- secure
- extensible
- compatible with scalable off-chain execution

It provides the **on-chain foundation** of the Silicium project.
