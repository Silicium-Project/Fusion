# Silicium Solana Layer SDK

TypeScript SDK for interacting with the **Silicium Solana Layer** Anchor program.

Current Devnet Program ID:

```txt
48Bdt8Dg9FW8n6Mpvvdh6dgTXrsBvBfqMrwhnWQ2WQm1
```

Keep this value aligned between `Anchor.toml`, `programs/solana-layer/src/lib.rs`, the generated IDL, SDK configuration, smoke tests and dashboard configuration.

---

## 1. Purpose

The SDK wraps the Anchor program instructions, PDA derivation helpers, account fetch helpers and event listeners. It gives the backend, frontend, worker nodes, verifier nodes, dashboard and future indexers a stable TypeScript interface for the Solana layer.

The SDK supports:

- worker and verifier registration;
- optional active worker staking;
- job creation and escrow funding;
- fragment claim, submit, resubmit and reclaim;
- verifier voting;
- verifier reward claiming;
- controlled sub-fragmentation;
- job finalization and cancellation;
- treasury initialization;
- vote slashing;
- passive network staking;
- account fetching;
- Anchor event subscriptions.

Main class:

```ts
SiliciumLayerSdk
```

Typical import:

```ts
import { SiliciumLayerSdk } from "./src";
```

---

## 2. Project structure

Recommended location inside the Anchor project:

```txt
solana-layer/
├── Anchor.toml
├── programs/
│   └── solana-layer/
├── scripts/
│   ├── devnet_smoke_test.ts
│   └── devnet_minimal_job_flow.ts
├── target/
│   ├── idl/
│   │   └── solana_layer.json
│   └── types/
│       └── solana_layer.ts
├── tests/
└── silicium-sdk/
    ├── src/
    │   ├── events.ts
    │   ├── index.ts
    │   ├── pdas.ts
    │   └── types.ts
    ├── examples/
    ├── package.json
    ├── tsconfig.json
    └── README.md
```

The SDK should stay close to the Anchor project because it depends on the generated IDL and Anchor account names.

---

## 3. Requirements

- Node.js
- Yarn or npm
- Solana CLI
- Anchor CLI
- A built Anchor program
- A wallet configured for Localnet or Devnet

Install dependencies from the SDK folder:

```bash
cd silicium-sdk
yarn install
```

Build the SDK:

```bash
yarn build
```

After on-chain changes, rebuild the Anchor program first:

```bash
cd ../
anchor build
```

---

## 4. Devnet setup

Check the deployed program:

```bash
solana program show 48Bdt8Dg9FW8n6Mpvvdh6dgTXrsBvBfqMrwhnWQ2WQm1 --url devnet
```

Check that local files match:

```bash
grep -R "declare_id" programs/solana-layer/src/lib.rs
grep -n "solana_layer" Anchor.toml
solana address -k target/deploy/solana_layer-keypair.json
```

If Anchor reports a Program ID mismatch:

```bash
anchor keys sync
anchor build
```

---

## 5. Localnet setup

Start a local validator:

```bash
solana-test-validator --reset
```

In another terminal:

```bash
cd ~/eip/Network/solana-layer
solana config set --url http://127.0.0.1:8899
solana airdrop 10
anchor keys sync --provider.cluster localnet
anchor build
anchor program deploy target/deploy/solana_layer.so --provider.cluster localnet
```

Set environment variables when using `AnchorProvider.env()`:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

---

## 6. Smoke tests

Read-only Devnet smoke test:

```bash
cd ~/eip/Network/solana-layer
anchor build
npx ts-node scripts/devnet_smoke_test.ts
```

Write Devnet smoke test:

```bash
npx ts-node scripts/devnet_smoke_test.ts --write
```

Minimal Devnet job flow:

```bash
npx ts-node scripts/devnet_minimal_job_flow.ts
```

The minimal job flow uses:

```txt
fresh compute worker
fresh verifier 1
fresh verifier 2
fragment_quorum = 2
verifier_reward_budget >= verifier_reward_per_vote * 2
```

---

## 7. SDK initialization

```ts
import * as anchor from "@coral-xyz/anchor";
import { SiliciumLayerSdk } from "./src";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer;
const sdk = SiliciumLayerSdk.fromWorkspace(provider, program);
```

The SDK exposes:

```ts
sdk.provider
sdk.program
sdk.programId
sdk.events
sdk.pdas
```

Wallet:

```ts
const wallet = sdk.walletPubkey();
```

---

## 8. Worker reputation fields

A worker account exposes three role-specific reputation values:

```ts
worker.computeReputation
worker.verifyReputation
worker.globalReputation
```

Recommended fetch helper:

```ts
const workerAccount = sdk.pdas.worker(owner);
const worker = await sdk.fetchWorker(workerAccount, true);

console.log(worker.computeReputation.toString());
console.log(worker.verifyReputation.toString());
console.log(worker.globalReputation.toString());
```

Or:

```ts
const reputation = await sdk.fetchWorkerReputation(owner);
```

Neutral bootstrap values:

```txt
compute_reputation = 5000
verify_reputation  = 5000
global_reputation  = 5000
```

---

## 9. PDA helpers

The SDK exposes PDA helpers through `sdk.pdas`:

```ts
const job = sdk.pdas.job(client, jobId);
const fragment = sdk.pdas.fragment(job, fragmentIndex);
const splitProposal = sdk.pdas.splitProposal(parentFragment);
const worker = sdk.pdas.worker(workerPublicKey);
const escrowAuth = sdk.pdas.escrowAuth(job);
const stakeAuth = sdk.pdas.stakeAuth(workerAccount);
const stakeVault = sdk.pdas.stakeVault(workerPublicKey);
const vote = sdk.pdas.vote(fragment, verifier, round);
const roundResolution = sdk.pdas.roundResolution(fragment, round);
const result = sdk.pdas.result(job);
const treasuryState = sdk.pdas.treasuryState(mint);
const treasuryAuth = sdk.pdas.treasuryAuth(mint);
const stakingPool = sdk.pdas.stakingPool(mint);
const stakingPoolAuth = sdk.pdas.stakingPoolAuth(mint);
const networkStaker = sdk.pdas.networkStaker(owner, mint);
```

Use PDA helpers instead of manually rebuilding seeds in frontend/backend code.

---

## 10. Main instruction helpers

### Register a worker

Registers the signer as both compute-capable and verify-capable by default.

```ts
await sdk.registerWorker();
```

Another signer:

```ts
await sdk.registerWorker({
  worker: workerKeypair.publicKey,
  signers: [workerKeypair],
});
```

The worker starts with neutral role-specific reputation:

```txt
compute = 5000
verify  = 5000
global  = 5000
```

### Stake worker tokens

Active worker staking is optional for bootstrap fragments and useful for higher-risk fragments, split proposal eligibility and economic security.

```ts
await sdk.stakeWorker({
  mint,
  workerToken,
  amount: 1_000_000,
});
```

### Create a job

```ts
const escrow = Keypair.generate();

const created = await sdk.createJob({
  jobId,
  expectedFragments: 1,
  rewardPerFragment: 1_000_000,
  verifierRewardPerVote: 100_000,
  verifierRewardBudget: 200_000,
  deadlineUnix,
  fragmentQuorum: 2,
  mint,
  escrow,
  clientToken,
});
```

Requirements:

```txt
fragmentQuorum >= 2
verifierRewardBudget >= expectedFragments * fragmentQuorum * verifierRewardPerVote
```

### Claim a fragment

```ts
const claimed = await sdk.claimFragment({
  worker: computeWorker.publicKey,
  job,
  fragmentIndex: 0,
  workerToken,
  signers: [computeWorker],
});
```

Access control uses `computeReputation` plus the fragment's `requiredComputeReputation` and `requiredStake` policy.

### Submit a result

```ts
await sdk.submitFragmentResult({
  worker: computeWorker.publicKey,
  job,
  fragmentIndex: 0,
  workerToken,
  resultHash,
  proofRef,
  signers: [computeWorker],
});
```

`resultHash` and `proofRef` are 32-byte values. The heavy result stays off-chain.

### Resubmit a rejected result

```ts
await sdk.resubmitFragmentResult({
  worker: computeWorker.publicKey,
  job,
  fragmentIndex: 0,
  workerToken,
  resultHash,
  proofRef,
  signers: [computeWorker],
});
```

### Vote on a fragment

```ts
await sdk.voteFragment({
  verifier: verifier.publicKey,
  job,
  fragment,
  escrow,
  workerToken,
  choice: true,
  signers: [verifier],
});
```

Access control uses `verifyReputation`. A verifier must not be the submitting worker or the job client.

### Claim verifier reward

```ts
await sdk.claimVerifierReward({
  verifier: verifier.publicKey,
  job,
  fragment,
  escrow,
  verifierToken,
  signers: [verifier],
});
```

A correct winning verifier reward increases `verifyReputation`.

### Finalize a job

```ts
await sdk.finalizeJob({
  job,
  escrow,
  clientToken,
  finalHash,
  outputUri: "ipfs://silicium-output",
});
```

`outputUri` points to the off-chain final result. The client verifies it with `finalHash`.

### Cancel a job

```ts
await sdk.cancelJob({
  job,
  escrow,
  clientToken,
});
```

---

## 11. Split and sub-fragment helpers

### Propose a split

```ts
await sdk.proposeFragmentSplit({
  splitter: splitter.publicKey,
  job,
  parentFragment,
  manifestHash,
  childCount: 4,
  signers: [splitter],
});
```

The manifest itself stays off-chain. Only the 32-byte `manifestHash` is stored on-chain.

### Approve a split

```ts
await sdk.approveFragmentSplit({
  job,
  parentFragment,
  splitProposal,
});
```

### Create a sub-fragment

```ts
await sdk.createSubFragment({
  job,
  parentFragment,
  splitProposal,
  childIndex,
  inputHash,
  proofRef,
  complexityScore,
  requiredComputeReputation,
  requiredStake,
});
```

A `SplitParent` cannot be claimed directly. Only leaf fragments can be claimed and submitted.

---

## 12. Passive network staking helpers

Passive staking is separate from worker/verifier active participation.

```ts
await sdk.initStakingPool({ mint, stakeVault, rewardVault });
await sdk.stakeNetwork({ mint, ownerToken, amount: 1_000_000 });
await sdk.fundStakingRewards({ mint, funderToken, amount: 100_000 });
await sdk.claimStakingReward({ mint, ownerRewardToken });
await sdk.requestUnstake({ mint, amount: 500_000 });
await sdk.withdrawUnstaked({ mint, ownerToken });
```

Passive stakers do not need a `Worker` account.

---

## 13. Account fetch helpers

```ts
const jobData = await sdk.fetchJob(job);
const fragmentData = await sdk.fetchFragment(fragment);
const workerData = await sdk.fetchWorker(workerPublicKey);
const workerDataFromPda = await sdk.fetchWorker(workerAccountPda, true);
const voteData = await sdk.fetchVote(vote);
const roundResolutionData = await sdk.fetchRoundResolution(roundResolution);
const resultData = await sdk.fetchResult(result);
const treasuryData = await sdk.fetchTreasuryState(mint);
const stakingPoolData = await sdk.fetchStakingPool(pool);
const networkStakerData = await sdk.fetchNetworkStaker(owner, mint);
const allWorkers = await sdk.fetchAllWorkers();
const jobFragments = await sdk.fetchFragmentsForJob(job);
```

`fetchWorker` has two modes:

```ts
await sdk.fetchWorker(workerOwnerPublicKey);
await sdk.fetchWorker(workerAccountPda, true);
```

Use the second form when you already have the worker PDA.

---

## 14. Event listeners

Listen to one event:

```ts
const sub = sdk.events.on("dualReputationUpdated", (event, slot, signature) => {
  console.log(event.newComputeReputation.toString());
});
```

Listen to all events:

```ts
const subscriptions = sdk.events.onAll((name, event, slot, signature) => {
  console.log(name, event, slot, signature);
});
```

Remove all:

```ts
await Promise.all(subscriptions.map((sub) => sub.remove()));
```

Supported SDK event names:

```txt
jobCreated
workerRegistered
workerStaked
treasuryInitialized
fragmentClaimed
fragmentReclaimed
fragmentSubmitted
fragmentVerified
fragmentRejected
verifierRewardClaimed
jobFinalized
jobCancelled
voteSlashed
dualReputationUpdated
bayesianReputationUpdated
fragmentSplitProposed
fragmentSplitApproved
fragmentSplitRejected
subFragmentCreated
fragmentSplitCompleted
stakingPoolInitialized
networkStakeDeposited
stakingRewardsFunded
stakingRewardClaimed
networkUnstakeRequested
networkUnstakeWithdrawn
```

---

## 15. Typical backend flow

```txt
1. Listen to jobCreated.
2. Fetch the job account.
3. Store the job in the off-chain database.
4. Expose available fragments to workers.
5. Workers call claimFragment.
6. Backend listens to fragmentClaimed.
7. Workers execute the real computation off-chain.
8. Workers submit resultHash and proofRef.
9. Backend listens to fragmentSubmitted.
10. Verifiers fetch the off-chain result/proof and call voteFragment.
11. Backend listens to fragmentVerified / fragmentRejected.
12. Verifiers claim rewards.
13. When all fragments and verifier rewards are complete, finalizeJob.
14. Backend indexes jobFinalized for users.
```

---

## 16. Typical worker node flow

```txt
1. registerWorker
2. optionally stakeWorker for better/higher-risk tasks
3. read available fragments from backend/indexer
4. claimFragment
5. compute off-chain
6. upload result/proof off-chain
7. submitFragmentResult(resultHash, proofRef)
8. wait for fragmentVerified or fragmentRejected
9. resubmit if rejected and allowed
```

A worker that calculates well increases `computeReputation`.

---

## 17. Typical verifier node flow

```txt
1. registerWorker
2. optionally stakeWorker for higher-risk verification work
3. listen to fragmentSubmitted
4. fetch off-chain proof/result
5. verify computation
6. voteFragment(true/false)
7. if vote wins, claimVerifierReward
```

A verifier that votes correctly and claims rewards increases `verifyReputation`.

---

## 18. Typical frontend flow

A frontend can use the SDK to:

```txt
1. connect wallet;
2. register user as worker/verifier;
3. show compute / verify / global reputation;
4. show active stake and passive network stake;
5. create jobs;
6. display job and fragment status;
7. display sub-fragment trees;
8. listen to live events;
9. show final output_uri and final_hash.
```

---

## 19. Hash handling

The SDK should treat hashes as integrity commitments. Heavy data stays off-chain.

```txt
on-chain  = hash + state + payments + votes
off-chain = files + inputs + outputs + proofs
```

Recommended pattern:

```ts
import { createHash } from "crypto";

export function sha256Bytes(data: Buffer | Uint8Array | string): number[] {
  const buffer = typeof data === "string" ? Buffer.from(data) : Buffer.from(data);
  return Array.from(createHash("sha256").update(buffer).digest());
}
```

Do not rely on `hash(uri)` to prove file contents. Use `hash(file_content)` or a canonical manifest containing the URI, content hash, size and MIME type.

---

## 20. Common errors

### `InvalidParams` in `create_job.rs`

Common causes:

```txt
fragmentQuorum < 2
expectedFragments invalid
verifierRewardBudget too small
deadline too short or too long
total deposit below MIN_JOB_DEPOSIT
```

Safe test values:

```ts
const expectedFragments = 1;
const rewardPerFragment = 1_000_000;
const verifierRewardPerVote = 100_000;
const fragmentQuorum = 2;
const verifierRewardBudget = expectedFragments * fragmentQuorum * verifierRewardPerVote;
```

### Program ID mismatch

Run:

```bash
anchor keys sync
anchor build
```

Then verify:

```bash
grep -R "declare_id" programs/solana-layer/src/lib.rs
grep -n "solana_layer" Anchor.toml
```

### Devnet deploy runs out of SOL

Close failed deploy buffers:

```bash
solana program show --buffers --url devnet
solana program close BUFFER_ADDRESS --url devnet
```

---

## 21. Production notes

Before production:

- use a dedicated RPC provider;
- avoid hardcoding Program IDs in build artifacts;
- keep IDL and SDK versions aligned;
- add an event indexer;
- store job inputs/outputs/proofs in durable off-chain storage;
- audit all slashing and reward logic;
- make split thresholds stricter than local test values;
- increase cooldown and TTL constants;
- keep bootstrap stake low, but restrict high-risk fragments by `requiredStake` and `requiredComputeReputation`.

---

## 22. Validation status

Validated locally:

```txt
registerWorker OK
bootstrap participation without active stake OK
stakeWorker OK
createJob quorum 2 OK
claimFragment OK
submitFragmentResult OK
voteFragment with 2 verifiers OK
fragmentVerified OK
fragmentRejected OK
resubmit after rejection OK
reclaim expired claim OK
computeReputation increase/decrease OK
verifyReputation increase/decrease OK
weighted verifier penalty OK
split proposal / approval / child creation OK
SplitParent cannot be claimed OK
passive staking OK
slash wrong vote OK
finalizeJob OK
```

---

## 23. Milestones

Milestones are planned for the validation layer after the current hash/proof-ref workflow.

Current validation uses:

```txt
result_hash
proof_ref
vote_fragment(choice)
```

A future milestone workflow can add:

```txt
milestone_root
milestone_count
challenge_seed
validate_fragment / submit_milestone_check
```

