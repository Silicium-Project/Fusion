# Payment Contract — Token/Credit Accounting Specification

This document defines the accounting contract for token-credit management and escrow safety.

## Scope

- Token-credit accounting model (units, precision, rounding).
- Conversion constraints and escrow lifecycle.
- Withdrawal/refund safety invariants.
- Event model for off-chain reconciliation.
- Threat model and acceptance tests.

## Roles

- **User**: owns credits/tokens and requests conversions/withdrawals.
- **Treasury authority**: manages settlement liquidity and policy.
- **Escrow authority**: moves funds only through valid lifecycle transitions.
- **Governance authority**: updates limits, rates, and pause controls.

## Units and Precision

- **Token unit**: integer base units (no floating point on-chain).
- **Credit unit**: integer micro-credit unit (`1 credit = 10^6 micro-credit`).
- **Rate representation**: rational `(numerator, denominator)` with bounded denominator.
- **Rounding mode**: deterministic **floor** for user-credit-to-token conversion.

Rule: all arithmetic is integer-only and overflow-checked.

## State Model

### `PaymentConfig`

- `admin`, `paused`.
- `token_mint`.
- `rate_num`, `rate_den`.
- `max_conversion_per_tx`.
- `max_withdrawal_per_epoch`.

### `UserAccount`

- `owner`.
- `credits_balance`.
- `tokens_balance_internal` (accounting view).
- `nonce` (replay protection for signed intents).
- `last_update_slot`.

### `EscrowAccount`

- `escrow_id`.
- `owner`.
- `status`: `OPEN | FUNDED | LOCKED | RELEASED | REFUNDED | CLOSED`.
- `amount_locked`.
- `amount_released`.
- `amount_refunded`.
- `beneficiary`.

## Conversion Model

`tokens_out = floor(credits_in * rate_num / rate_den)`

Constraints:

- `credits_in > 0`.
- `credits_in <= credits_balance`.
- `credits_in <= max_conversion_per_tx`.
- `rate_den > 0`.
- conversion denied while `paused`.

Post-conditions:

- `credits_balance -= credits_in`.
- `tokens_balance_internal += tokens_out`.
- accounting delta emitted in event stream.

## Escrow Lifecycle

1. `open_escrow`: create `EscrowAccount` in `OPEN`.
2. `fund_escrow`: move user token balance into escrow, `OPEN -> FUNDED`.
3. `lock_escrow`: reserve funded amount for active execution, `FUNDED -> LOCKED`.
4. `release_escrow`: pay beneficiary on success, `LOCKED -> RELEASED`.
5. `refund_escrow`: return funds on cancel/failure, `LOCKED|FUNDED -> REFUNDED`.
6. `close_escrow`: terminal close after full release/refund, `RELEASED|REFUNDED -> CLOSED`.

No direct withdrawal path is allowed from `LOCKED` without explicit lifecycle transition.

## Invariants

- **PAY-INV-01 (Conservation)**: per escrow, `amount_locked == amount_released + amount_refunded + amount_pending`.
- **PAY-INV-02 (Non-negative)**: all balances and counters are non-negative integers.
- **PAY-INV-03 (Overflow-safe)**: any arithmetic overflow aborts transition.
- **PAY-INV-04 (Rate validity)**: `rate_den > 0`, bounded `rate_num/rate_den`.
- **PAY-INV-05 (Deterministic rounding)**: conversion uses floor only.
- **PAY-INV-06 (Authorization)**: only authorized signers execute privileged transitions.
- **PAY-INV-07 (Replay resistance)**: nonce/signature cannot be reused.
- **PAY-INV-08 (Terminal freeze)**: `CLOSED` escrow is immutable.
- **PAY-INV-09 (Pause safety)**: mutable financial transitions blocked when paused (except recovery).
- **PAY-INV-10 (Withdrawal bound)**: withdrawals obey configured epoch and amount limits.

## Security Considerations

| Threat | Description | Mitigation | Invariants |
| --- | --- | --- | --- |
| Double spend | Same funds consumed twice via race/replay | account locking + nonce checks + idempotent handlers | PAY-INV-01, PAY-INV-07 |
| Rounding abuse | User gains value by split-order conversions | fixed floor policy + integer arithmetic | PAY-INV-05 |
| Rate manipulation timing | Exploiting stale or invalid rate update | governance-only rate change + bounded params + eventing | PAY-INV-04, PAY-INV-06 |
| Unauthorized withdrawal | Attacker drains escrow/user balance | signer/owner checks + state-gated transitions | PAY-INV-06, PAY-INV-10 |
| Escrow insolvency | Released/refunded exceeds locked amount | conservation checks on every transition | PAY-INV-01 |
| Pause bypass | Financial mutation during emergency | global pause guard for state-changing ops | PAY-INV-09 |

## Event Model (Reconciliation)

Emit structured events on each mutation:

- `UserInitialized`
- `TokensDeposited`
- `CreditsConverted`
- `EscrowOpened`
- `EscrowFunded`
- `EscrowLocked`
- `EscrowReleased`
- `EscrowRefunded`
- `EscrowClosed`
- `WithdrawalExecuted`

Required fields:

- `event_id`, `slot`, `tx_signature`
- `actor`, `account`
- before/after balances
- conversion inputs/outputs and rate snapshot
- escrow lifecycle fields (`escrow_id`, `status_before`, `status_after`, deltas)

## Acceptance Test Matrix

| Test ID | Scenario | Expected Result | Invariants |
| --- | --- | --- | --- |
| PAY-T01 | Initialize user account | balances zeroed, owner set | PAY-INV-02 |
| PAY-T02 | Deposit token amount | internal token balance increases | PAY-INV-02 |
| PAY-T03 | Convert credits with valid rate | floor conversion applied | PAY-INV-05 |
| PAY-T04 | Convert with zero denominator | rejected | PAY-INV-04 |
| PAY-T05 | Convert beyond balance or max cap | rejected | PAY-INV-02, PAY-INV-10 |
| PAY-T06 | Overflow in conversion path | rejected | PAY-INV-03 |
| PAY-T07 | Open/fund/lock escrow happy path | lifecycle progresses correctly | PAY-INV-01 |
| PAY-T08 | Release more than locked | rejected | PAY-INV-01 |
| PAY-T09 | Refund from invalid status | rejected | PAY-INV-06 |
| PAY-T10 | Close escrow before terminal state | rejected | PAY-INV-08 |
| PAY-T11 | Replay signed withdrawal nonce | rejected | PAY-INV-07 |
| PAY-T12 | Unauthorized release/refund call | rejected | PAY-INV-06 |
| PAY-T13 | Pause enabled then convert/deposit | rejected (except recovery paths) | PAY-INV-09 |
| PAY-T14 | Epoch withdrawal limit exceeded | rejected | PAY-INV-10 |
| PAY-T15 | Event stream reconciliation | deltas equal on-chain state transitions | PAY-INV-01, PAY-INV-05 |

## Legacy Issue Scope Reduction

Issue `#13` should be implementation-only:

- implement instruction handlers according to this accounting contract,
- implement tests mapped to `PAY-T01..PAY-T15`,
- avoid functional scope expansion without a dedicated specification issue.
