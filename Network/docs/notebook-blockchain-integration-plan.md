# JupiterNotebook Flow and Blockchain Integration Plan

This document defines the target product architecture for JupiterNotebook as a client-facing layer over Silicium execution and settlement rails.

## Goals

- Provide a clear user flow from notebook submission to on-chain settlement.
- Define backend/API capabilities required for a first production slice.
- Specify blockchain touchpoints (`submit`, `monitor`, `settle`) and data boundaries.
- Bound MVP scope and explicitly document non-goals.

## Actors

- **Notebook user**: submits notebook jobs and tracks outcomes.
- **Backend API**: validates requests, prepares transactions, indexes chain state.
- **Wallet client**: signs user-authorized on-chain instructions.
- **On-chain programs**: `JobRegistry`, `FragmentCertifier`, `ResultAssembler`, `StakeManager`.
- **Compute node**: executes assigned fragments and submits proofs.

## End-to-End User Flow

1. **Prepare job**
   - User selects notebook, runtime profile, constraints, and budget.
   - UI computes and uploads deterministic artifact bundle (source, deps lock, metadata hash).
2. **Submit intent**
   - UI calls backend `POST /jobs` with artifact hash + execution constraints.
   - Backend validates shape/policy and returns unsigned transaction payload(s).
3. **On-chain submission**
   - Wallet signs and broadcasts `JobRegistry.create_job` + escrow funding instructions.
   - Backend records transaction signatures and initializes indexing.
4. **Execution monitoring**
   - Compute nodes claim fragments and publish proofs.
   - UI reads status timeline via backend aggregate endpoints.
5. **Completion and settlement**
   - `ResultAssembler` marks completion when fragment criteria pass.
   - `JobRegistry`/`StakeManager` settle rewards/refunds.
   - UI exposes result artifacts, payouts, and final status.

## Backend/API Capabilities

### Required APIs (MVP)

- `POST /jobs`
  - Validate request payload and policy.
  - Return transaction intent(s) for wallet signature.
- `GET /jobs/:id`
  - Return aggregated status from on-chain + off-chain index.
- `POST /fragments/:id/proof`
  - Accept proof payloads and enqueue/publish certifier transaction intent.
- `GET /jobs/:id/events`
  - Return normalized event stream for UI timeline/reconciliation.
- `POST /jobs/:id/cancel`
  - Produce cancellation/refund intent if policy allows.

### Supporting Services

- Chain indexer (RPC websocket + backfill scanner).
- Artifact metadata store (hash-indexed; object storage is externalized).
- Deterministic event normalizer (maps chain events to UI domain events).
- Retry/idempotency layer for transaction intent generation.

## Blockchain Integration Touchpoints

### Submit

- Programs: `JobRegistry` (+ escrow funding token transfer).
- Inputs: job metadata hash, budget, deadline, fragment count.
- Outputs: `job_id`, transaction signatures, initial on-chain status.

### Monitor

- Programs/events: `JobRegistry`, `FragmentCertifier`, `ResultAssembler`.
- Backend responsibility:
  - subscribe and backfill events,
  - map program-specific fields to canonical status model,
  - detect stalls (deadline/fragment inactivity).

### Settle

- Programs: `ResultAssembler` + `JobRegistry` + `StakeManager`.
- Conditions: completion criteria met or cancellation/failure path.
- Outputs: final status, payout/refund deltas, immutable settlement record.

## Data Boundaries

### On-chain authoritative data

- Job lifecycle state.
- Escrow balances and settlement deltas.
- Fragment certification/acceptance checkpoints.
- Node staking/rewarding outcomes.

### Off-chain data

- Notebook artifact payloads and large execution outputs.
- UI projections and cached query views.
- Operational telemetry and retry metadata.

Rule: off-chain state must be derivable from on-chain events + immutable artifact hashes.

## Interface Contracts

- All mutating user actions produce **transaction intents** first; signing is always wallet-mediated.
- APIs must be idempotent by `(user, request_id)` to prevent duplicate on-chain actions.
- Job status API must expose both:
  - canonical lifecycle state,
  - latest chain signature/slot anchor.

## MVP Boundary

### In scope (MVP)

- Single-chain deployment target.
- Notebook job submit/track/cancel.
- Escrow-backed settlement for success/cancel/failure.
- Fragment proof ingestion and final result publication link.
- Basic policy controls (budget caps, timeout caps, pause mode).

### Deliverable Checklist (MVP)

- [ ] `POST /jobs` intent flow with wallet signing path.
- [ ] `GET /jobs/:id` aggregate status endpoint.
- [ ] Event indexer for submit/monitor/settle transitions.
- [ ] Settlement reconciliation view (paid/refunded/locked).
- [ ] Cancel/refund path with policy checks.
- [ ] Operational runbook for indexer recovery/backfill.

## Non-Goals (MVP)

- Multi-chain settlement.
- Cross-job batching/portfolio optimization.
- Advanced governance UX and voting frontend.
- Arbitrary notebook marketplace/economic auctions.
- Fully trustless off-chain output storage guarantees.

## Operational and Security Notes

- Enforce deterministic artifact hashing at submission boundary.
- Require replay protection keys/nonces for intent endpoints.
- Reject stale or policy-violating intents before wallet handoff.
- Emit audit events for every backend-produced transaction intent.

## Legacy Issue Scope Reduction

Issue `#15` should be implementation-only after this plan:

- implement APIs/indexer/transactions per this architecture,
- keep product scope within MVP boundary above,
- open dedicated spec issues for any post-MVP expansion.
