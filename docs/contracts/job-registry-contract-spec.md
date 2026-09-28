# JobRegistry Contract — Functional Specification and Threat Model

This document defines the functional contract for the on-chain `JobRegistry` program.

## Scope

- Job creation and lifecycle state transitions.
- Escrow custody and settlement constraints.
- Fragment assignment orchestration anchors (without worker internals).
- Security invariants, threat model, and acceptance test matrix.

## Roles and Trust Boundaries

- **Client**: submits a job and funds escrow.
- **Compute node**: claims/executes fragments and becomes payout-eligible.
- **Settlement authority**: finalizes payout once completion criteria are met.
- **Governance authority**: updates protocol-level policy and limits.

Trust boundary: only on-chain state transitions are authoritative for status and escrow movement.

## State Model

### `RegistryConfig`

- `admin`: governance authority key.
- `paused`: protocol-wide pause flag.
- `token_mint`: allowed payment mint.
- `max_fragments_per_job`: upper bound.
- `max_deadline_secs`: upper bound from creation time.

### `JobAccount`

- `job_id`: unique id.
- `owner`: client key.
- `status`: `CREATED | FUNDED | SCHEDULED | RUNNING | COMPLETED | CANCELLED | FAILED | SETTLED`.
- `created_slot`, `updated_slot`.
- `budget_total`: escrowed amount.
- `budget_locked`: reserved/unpaid amount.
- `budget_paid`: paid-out amount.
- `budget_refunded`: refunded amount.
- `fragment_total`, `fragment_assigned`, `fragment_submitted`, `fragment_accepted`.
- `metadata_hash`: immutable hash of off-chain job spec.
- `deadline_slot`: optional timeout boundary.

### `EscrowVault`

- Program-owned token account derived from `job_id` PDA.
- Source of all payouts/refunds for that job.

### `FragmentAssignment` (logical mapping)

- `job_id`, `fragment_id`, `node`.
- `status`: `UNASSIGNED | ASSIGNED | SUBMITTED | ACCEPTED | REJECTED | EXPIRED`.
- `reward_cap`.

## Allowed Transitions

1. `create_job`:
   - `none -> CREATED`
   - Requires: unique `job_id`, valid `fragment_total`, valid `metadata_hash`.
2. `fund_job`:
   - `CREATED -> FUNDED`
   - Requires: token transfer into `EscrowVault`.
3. `schedule_job`:
   - `FUNDED -> SCHEDULED`
   - Requires: `paused == false`.
4. `assign_fragment`:
   - `SCHEDULED|RUNNING` with assignment `UNASSIGNED -> ASSIGNED`.
   - Side effect: `fragment_assigned += 1`.
5. `submit_fragment`:
   - Assignment `ASSIGNED -> SUBMITTED`.
   - Side effect: `fragment_submitted += 1`.
6. `accept_fragment`:
   - Assignment `SUBMITTED -> ACCEPTED`.
   - Side effect: `fragment_accepted += 1`, optional `RUNNING`.
7. `complete_job`:
   - `RUNNING|SCHEDULED -> COMPLETED`
   - Requires: acceptance criteria met (`fragment_accepted == fragment_total` or policy quorum).
8. `cancel_job`:
   - `CREATED|FUNDED|SCHEDULED|RUNNING -> CANCELLED`
   - Requires: authorized actor + cancellation policy.
9. `fail_job`:
   - `RUNNING|SCHEDULED -> FAILED`
   - Requires: deadline reached or terminal policy violation.
10. `settle_job`:
    - `COMPLETED|CANCELLED|FAILED -> SETTLED`
    - Transfers payout/refund from escrow, final accounting freeze.

## Invariants

- **JR-INV-01 (Budget conservation)**: `budget_total == budget_paid + budget_refunded + budget_locked`.
- **JR-INV-02 (Escrow backing)**: token balance in vault equals `budget_paid_pending + budget_refunded_pending + budget_locked`.
- **JR-INV-03 (Monotonic counters)**: fragment counters never decrease.
- **JR-INV-04 (Counter bounds)**: `fragment_accepted <= fragment_submitted <= fragment_assigned <= fragment_total`.
- **JR-INV-05 (Authorized transitions)**: only permitted roles invoke each transition.
- **JR-INV-06 (Terminal freeze)**: after `SETTLED`, no mutable business fields change.
- **JR-INV-07 (Single assignment owner)**: one active node per `(job_id, fragment_id)` assignment.
- **JR-INV-08 (Replay resistance)**: duplicate submit/settle instructions are idempotent or rejected.
- **JR-INV-09 (Pause enforcement)**: mutating non-recovery actions blocked when `paused == true`.
- **JR-INV-10 (Deadline safety)**: transitions violating deadline policy are rejected.

## Threat Model

| Threat | Description | Primary Controls | Invariants |
| --- | --- | --- | --- |
| Replay of settle/submit | Reuse old signed instruction to drain or double count | Nonce/PDA state checks, idempotent guards | JR-INV-08, JR-INV-06 |
| Griefing by fragment hoarding | Node claims and never submits | Assignment expiry, reassignment, optional penalties | JR-INV-07, JR-INV-10 |
| Escrow abuse | Unauthorized payout or refund path | Strict role checks + state-gated transfers | JR-INV-01, JR-INV-02, JR-INV-05 |
| Authorization failure | Caller executes forbidden transition | Program-level signer + role validation | JR-INV-05 |
| Counter forgery | Accept/submitted mismatch | Deterministic transition preconditions | JR-INV-03, JR-INV-04 |
| Settlement race | Concurrent settle/refund/payout attempts | Atomic account locking + terminal checks | JR-INV-06, JR-INV-08 |
| Governance misuse | Unsafe config update | Admin-only update paths + event auditability | JR-INV-05, JR-INV-09 |

## Event Model (for indexing/reconciliation)

Emit structured events on every state transition:

- `JobCreated`, `JobFunded`, `JobScheduled`, `FragmentAssigned`, `FragmentSubmitted`, `FragmentAccepted`, `JobCompleted`, `JobCancelled`, `JobFailed`, `JobSettled`.
- Required fields: `job_id`, actor, slot, pre_status, post_status, budget deltas, fragment counters.

## Acceptance Test Matrix

| Test ID | Scenario | Expected Result | Invariants |
| --- | --- | --- | --- |
| JR-T01 | Create valid job | `CREATED`, counters initialized | JR-INV-03, JR-INV-04 |
| JR-T02 | Duplicate `job_id` create | Rejected | JR-INV-05 |
| JR-T03 | Fund job with valid mint | `FUNDED`, escrow updated | JR-INV-01, JR-INV-02 |
| JR-T04 | Fund with wrong mint/account | Rejected | JR-INV-02, JR-INV-05 |
| JR-T05 | Assign fragment in funded/scheduled flow | Assignment created once | JR-INV-07 |
| JR-T06 | Double assign same fragment concurrently | One succeeds, one rejected | JR-INV-07, JR-INV-08 |
| JR-T07 | Submit then accept fragment | Counters monotonic and bounded | JR-INV-03, JR-INV-04 |
| JR-T08 | Accept without submit | Rejected | JR-INV-04 |
| JR-T09 | Unauthorized transition caller | Rejected | JR-INV-05 |
| JR-T10 | Complete before acceptance threshold | Rejected | JR-INV-04 |
| JR-T11 | Complete then settle | Terminal state with balanced accounting | JR-INV-01, JR-INV-06 |
| JR-T12 | Repeat settle instruction | No double payout | JR-INV-08 |
| JR-T13 | Cancel and refund path | Refund bounded by escrow | JR-INV-01, JR-INV-02 |
| JR-T14 | Pause enabled then mutation attempted | Rejected (except recovery) | JR-INV-09 |
| JR-T15 | Deadline exceeded then submit/accept | Rejected per policy | JR-INV-10 |

## Legacy Issue Scope Reduction

Issue `#12` should be treated as implementation-only:

- implement instructions/accounts as specified here,
- implement tests matching `JR-T01..JR-T15`,
- do not expand product scope beyond this contract without a dedicated spec issue.
