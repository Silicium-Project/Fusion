# Silicium – Solana Anchor Smart Contracts  
## Decentralized Task Distribution & Reward System

---

## Overview

**Silicium** is a decentralized compute coordination protocol built on **Solana** using the **Anchor framework**.

The system allows:
- users to submit compute tasks,
- tasks to be split **off-chain** into subtasks,
- subtasks to be assigned **on-chain** to workers,
- results to be verified,
- rewards to be paid automatically using escrowed tokens.

The design follows a **hybrid architecture**:
- **on-chain**: state, task lifecycle, escrow, rewards, reputation
- **off-chain**: task splitting, scheduling, storage, execution

This contains **only the on-chain smart contracts**.

---

## Architecture Summary

User (Frontend Wallet)
|
| signed transactions
v
Solana RPC <───> Silicium Program (Anchor)
|
v
Backend / Scheduler (Off-chain)


- The **frontend** interacts with the blockchain via RPC.
- The **backend scheduler** decides how tasks are split and assigned.
- The **Silicium program** enforces trust, payments, and rules.

---

## Repository Structure

silicium-chain/
├── Anchor.toml
├── programs/
│ └── silicium/
│ └── src/
│ ├── lib.rs
│ ├── constants.rs
│ ├── errors.rs
│ ├── events.rs
│ ├── state/
│ │ ├── config.rs
│ │ ├── worker.rs
│ │ ├── task.rs
│ │ └── assignment.rs
│ └── instructions/
│ ├── init_config.rs
│ ├── register_worker.rs
│ ├── submit_task.rs
│ ├── fund_task.rs
│ ├── assign_work.rs
│ ├── submit_result.rs
│ ├── verify_result.rs
│ ├── finalize_task.rs
│ ├── claim_reward.rs
│ └── slash_worker.rs
└── tests/


---

## Core Concepts

### Task Lifecycle

1. Submit task (metadata hash only)
2. Fund task (tokens escrowed)
3. Assign subtasks (scheduler)
4. Submit results (workers)
5. Verify results (verifiers)
6. Finalize task
7. Claim rewards

---

## On-Chain Accounts (State)

### Config (PDA)

Global protocol configuration:
- admin authority
- scheduler authority
- token mint
- protocol fee

### Worker (PDA)

Represents a registered compute node:
- owner wallet
- reputation score
- job statistics

### Task (PDA)

Represents a user-submitted task:
- metadata hash
- total budget
- remaining budget
- status

### Assignment (PDA)

Represents a single subtask:
- assigned worker
- reward
- verification votes
- result hash
- reward split

---

## Instructions (Smart Contract Functions)

| Instruction | Purpose |
|------------|--------|
| `init_config` | Initialize protocol configuration |
| `register_worker` | Register a worker |
| `submit_task` | Create a new task |
| `fund_task` | Deposit budget into escrow |
| `assign_work` | Assign a subtask (scheduler) |
| `submit_result` | Worker submits result hash |
| `verify_result` | Verifiers approve or reject |
| `finalize_task` | Compute reward distribution |
| `claim_reward` | Worker claims payment |
| `slash_worker` | Penalize malicious workers |

Each instruction is implemented in **one file**, following a **1 action = 1 module** design.

---

## Off-Chain Responsibilities

The blockchain **does NOT**:
- split tasks,
- choose workers,
- store large data,
- execute computation.

These are handled **off-chain** by:
- a scheduler backend,
- worker nodes,
- distributed storage (IPFS / DB / S3).

Only **hashes and state transitions** are stored on-chain.

---

## Token and Payments

- Payments use **SPL Tokens**
- Task budgets are held in **escrow**
- Rewards are released only after verification
- Fees are deducted automatically

---

## Security Design

- Funds locked in PDA-controlled escrow
- Deterministic account derivation
- Verification threshold enforcement
- Reputation system
- Slashing mechanism

---

## Build and Deploy

anchor build
anchor deploy --provider.cluster devnet

## Acronyms and Definitions
### PDA = Program Derived Address: 
A deterministic account address derived from:
   - seeds and program ID
Used for:
   - Config
   - Task
   - Worker
   - Assignment
   - Vault authority

PDAs cannot be owned by users, only by the program.

### ATA — Associated Token Account
A standard SPL token account:
   - linked to a wallet or PDA
holds tokens of a specific mint
Used for:
   - user balances
   - escrow vaults
   - reward payouts

### RPC — Remote Procedure Call

The interface used to:
   - read blockchain state
   - send transactions
   - subscribe to events

Example:
https://api.devnet.solana.com

### SPL — Solana Program Library
Solana’s standard library for:
   - tokens
   - governance
   - utilities

### SBF — Solana BPF
Solana’s execution format for programs (similar to eBPF).
Anchor compiles Rust code into SBF.

### CPI — Cross-Program Invocation

Calling another Solana program from a smart contract
example: calling the SPL Token program to transfer tokens.

### Escrow
A mechanism where funds are:
locked, controlled by a program, released only when conditions are met.

### Scheduler
An off-chain backend responsible for:
splitting tasks, selecting workers and calling assign_work.

# License
MIT