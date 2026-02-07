# Silicium Chain – On-chain Job, Worker & Reward Layer

Silicium Chain is the **on-chain coordination and payment layer** of the Silicium project.  
It secures funds, tracks computation progress, manages worker participation, and enforces verifiable rewards for distributed computation executed off-chain.

Computation, task splitting, and execution are **off-chain**.  
The blockchain acts as a **source of truth, escrow, worker registry, and verifiable payment layer**.

---

## Purpose of the Layer

This Solana program (built with Anchor) enables:

- Registration of **distributed computation jobs**
- Secure escrow of client funds using **SPL Tokens**
- Registration and tracking of **workers**
- Management of **computation fragments**
- **Per-fragment rewards** for workers
- **Multi-verifier fragment validation (quorum-based)**
- Secure job **finalization or cancellation**

This layer is **functional** and ready to be deployed on **devnet**.

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
- `verifier_authority`: verifier authority (MVP fallback)
- `challenge_window_sec`: challenge window (MVP = disabled)

---

### Worker
Represents a registered computation or verification participant.

Each wallet may own **exactly one Worker account**.

Main fields:
- `owner`: worker wallet
- `stake_amount`: staked amount (MVP = informational, no slashing yet)
- `reputation`: signed score based on verification outcomes
- `total_submitted`: number of fragments submitted
- `total_verified`: number of fragments accepted
- `total_rejected`: number of fragments rejected
- `status`: `Active | Banned`
- `bump`

Purpose:
- Prevents disposable / spam workers
- Tracks historical behavior
- Prepares future slashing and reputation-based logic

---

### Fragment
Represents **one unique fragment** of a job  
(1 `fragment_index` = 1 on-chain fragment account).

Key guarantees:
- Only one fragment per `(job, fragment_index)`
- A fragment cannot be verified more than once
- Voting state is initialized **once** on first submission

Main fields:
- `job`
- `fragment_index`
- `worker`
- `result_hash`
- `proof_ref`
- `status`: `Submitted | Verified | Rejected`

Verification (MVP quorum):
- `yes_votes`
- `no_votes`
- `required_quorum`
- `voting_deadline_unix`

---

### FragmentVote
Tracks **one verifier vote** on a fragment.

Guarantees:
- One vote per `(fragment, verifier)`
- Prevents double voting
- Enables quorum-based validation

Main fields:
- `fragment`
- `verifier`
- `choice` (accept / reject)
- `bump`

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

## Implemented Instructions

### `register_worker`
Registers a wallet as a worker.

Actions:
- Initializes the `Worker` account
- Enables participation in fragment submission and verification

---

### `create_job`
Creates a job and:
- Initializes the `Job` account
- Creates the SPL escrow account
- Deposits the required funds  
  (`expected_fragments × reward_per_fragment`)

---

### `submit_fragment_result`
Allows a registered worker to submit a result for a specific fragment.

Rules:
- Worker must be registered and active
- Fragments are uniquely identified by `(job, fragment_index)`
- Verified fragments cannot be overwritten
- Rejected fragments may be resubmitted by the same worker
- Initializes voting state on first submission

Side effects:
- Increments worker `total_submitted`

---

### `vote_fragment`
Allows a registered worker to verify a fragment.

Rules:
- Verifier must be a registered, active worker
- One vote per `(fragment, verifier)`
- Votes are tracked on-chain

Logic:
- Increments `yes_votes` or `no_votes`
- When quorum is reached:
  - Fragment becomes `Verified` or `Rejected`
  - On `Verified`, worker is paid immediately
  - Worker reputation and statistics are updated

---

### `finalize_job`
Finalizes a job **only when all fragments are verified**.

Actions:
- Stores the `JobResult`
- Refunds remaining escrow funds
- Closes the escrow account
- Sets the job status to `Finalized`

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

## Architectural Choices

- **Off-chain computation**, on-chain coordination
- Explicit worker registry
- Quorum-based fragment verification
- Immediate per-fragment payments
- No implicit trust between participants
- All financial flows are **fully auditable on-chain**

---

## Current Limitations

This version **does not yet include**:
- Stake slashing or penalties
- Decentralized verifier selection
- Automatic fragment assignment
- On-chain challenges or arbitration
- Reputation-weighted voting

These are planned for future iterations.

---

## Status

- Core logic implemented
- Worker registry and quorum verification live
- Test suite passing
- Ready for **devnet deployment**
- Designed for progressive decentralization

---

## Summary

Silicium Chain is a **secure coordination, worker, and payment layer** for distributed computation, designed to be:
- minimal
- auditable
- extensible
- compatible with scalable off-chain execution

It provides the **on-chain foundation** of the Silicium project.
