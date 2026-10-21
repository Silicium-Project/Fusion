# Silicium Solana Layer SDK

TypeScript SDK for interacting with the **Silicium Solana Layer** Anchor program.

Current Devnet Program ID:

```txt
A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2
```

Keep this value aligned between `Anchor.toml`, `programs/solana-layer/src/lib.rs`, the generated IDL, SDK configuration and smoke tests.

---

## 1. Purpose

The SDK wraps the Anchor program instructions, PDA derivation helpers, account fetch helpers and event listeners. It gives the backend, frontend, worker nodes, verifier nodes and future indexers a stable TypeScript interface for the Solana layer.

The SDK supports:

- worker and verifier registration;
- optional active worker staking;
- job creation and escrow funding;
- job storage declaration for P2P/off-chain task metadata;
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

## 2. Architecture: SDK, Solana Layer and Storage

The SDK is the integration layer between applications and the on-chain program.

```txt
Frontend / Backend / Worker node / Verifier node
        ↓
Silicium TypeScript SDK
        ↓
Solana Layer Anchor Program
        ↓
Events / accounts / escrow / reputation / votes
```

The SDK does not store large task files itself. Heavy data is stored off-chain or in a P2P storage layer. The on-chain program stores only integrity commitments and state.

```txt
Solana Layer
→ jobs, fragments, votes, reputation, payments, storage hashes

P2P / off-chain storage
→ task manifests, fragment inputs, outputs, proofs, final artifacts

SDK
→ creates transactions, derives PDAs, fetches accounts, listens to events, helps apps connect the two layers
```

The normal task data flow is:

```txt
Client/backend creates task files
  ↓
Uploads manifest and inputs to P2P/off-chain storage
  ↓
Computes manifest_hash, input_root_hash, storage_ref_hash
  ↓
createJob(...)
  ↓
declareJobStorage(...)
  ↓
Workers fetch JobStorage and download manifest
  ↓
Workers verify checksums and compute
  ↓
Workers submit resultHash + proofRef
  ↓
Verifiers download output/proof and verify checksums
  ↓
Verifiers vote
```

---

## 3. Project structure

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

## 4. Requirements

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

## 5. Devnet setup

Check the deployed program:

```bash
solana program show A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2 --url devnet
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

## 6. Localnet setup

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

## 7. Smoke tests

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

The Devnet test quote is fixed at six decimal places: one SIL (1,000,000
base units) for the accepted compute result and one SIL for each of two
accepted verifier votes. The escrow reserves 3 SIL per expected fragment.
Finalization returns any unspent balance. The cancellation refund rule is
present in local program source and takes effect on Devnet only after that
program update is deployed.

From `Network/solana-layer/`, run:

```bash
npx ts-node scripts/create_devnet_sil_mint.ts
```

The script stores the mint authority key in the ignored
`Network/.silicium/solana/` directory and prints only the public address. The
authority needs Devnet SOL for account creation and mint fees.

---

## 8. SDK initialization

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

## 9. Worker reputation fields

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

## 10. PDA helpers

The SDK exposes PDA helpers through `sdk.pdas`:

```ts
const job = sdk.pdas.job(client, jobId);
const jobStorage = sdk.pdas.jobStorage(job);
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

## 11. Main instruction helpers

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

### Declare job storage

After creating a job and uploading task metadata to the P2P/off-chain storage layer, declare the on-chain storage commitments:

```ts
const declared = await sdk.declareJobStorage({
  job,
  manifestHash,
  inputRootHash,
  storageRefHash,
  encryptionRefHash, // optional; defaults to 32 zero bytes if your SDK helper supports it
});

console.log(declared.signature);
console.log(declared.jobStorage.toBase58());
```

The SDK derives:

```txt
[b"job_storage", job]
```

Recommended 32-byte fields:

```txt
manifestHash       = sha256(canonical task manifest JSON)
inputRootHash      = sha256 or Merkle root of all fragment input hashes
storageRefHash     = sha256(canonical storage reference manifest)
encryptionRefHash  = sha256(canonical encryption metadata), or [0; 32] when unused
```

Fetch later:

```ts
const storage = await sdk.fetchJobStorage(job);

console.log(storage.manifestHash);
console.log(storage.inputRootHash);
console.log(storage.storageRefHash);
console.log(storage.encryptionRefHash);
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

An open job can be cancelled even after partial verified work. Rewards already
transferred for verified fragments remain paid. Any outstanding winning
verifier rewards must be claimed first; the rest of the escrow is refunded to
the client by the cancellation transaction.

---

## 12. Storage and P2P workflow

The SDK exposes only the on-chain storage commitments. Downloading files from IPFS, Arweave, libp2p, S3 or a Silicium storage gateway is handled by the application or storage module.

### 12.1 Canonical task manifest

Use a canonical JSON format for task manifests so every participant hashes the same bytes.

Example:

```json
{
  "version": 1,
  "job_type": "render_3d",
  "job_id": "example-job",
  "fragments": [
    {
      "fragment_index": 0,
      "input_uri": "ipfs://bafy...",
      "input_sha256": "abc...",
      "size": 123456,
      "mime": "application/octet-stream"
    },
    {
      "fragment_index": 1,
      "input_uri": "ipfs://bafy...",
      "input_sha256": "def...",
      "size": 789012,
      "mime": "application/octet-stream"
    }
  ]
}
```

Compute:

```ts
const manifestHash = sha256Bytes(canonicalManifestBytes);
```

### 12.2 Storage reference manifest

Use a separate storage reference manifest when the manifest itself has several retrieval options.

```json
{
  "protocol": "ipfs",
  "manifest_uri": "ipfs://bafyManifest...",
  "mirrors": [
    "https://gateway.example/ipfs/bafyManifest...",
    "https://storage.silicium.network/jobs/example-job/manifest.json"
  ]
}
```

Compute:

```ts
const storageRefHash = sha256Bytes(canonicalStorageRefBytes);
```

### 12.3 Declare storage after job creation

```ts
const { job } = await sdk.createJob({
  jobId,
  expectedFragments,
  rewardPerFragment,
  verifierRewardPerVote,
  verifierRewardBudget,
  deadlineUnix,
  fragmentQuorum: 2,
  mint,
  escrow,
  clientToken,
});

await sdk.declareJobStorage({
  job,
  manifestHash,
  inputRootHash,
  storageRefHash,
});
```

### 12.4 Worker download and checksum

A worker should verify storage before computing:

```ts
const storage = await sdk.fetchJobStorage(job);
const storageRef = await p2p.downloadStorageRef(storage.storageRefHash);

assertBytesEqual(sha256Bytes(storageRef.bytes), storage.storageRefHash);

const manifest = await p2p.downloadManifest(storageRef.manifestUri);
assertBytesEqual(sha256Bytes(manifest.bytes), storage.manifestHash);

const fragmentInput = manifest.fragments.find((f) => f.fragment_index === fragmentIndex);
const inputBytes = await p2p.download(fragmentInput.input_uri);

assertHexEqual(sha256Hex(inputBytes), fragmentInput.input_sha256);
```

Then the worker computes, uploads output/proof, and submits:

```ts
const resultHash = sha256Bytes(outputBytes);
const proofRef = sha256Bytes(canonicalProofManifestBytes);

await sdk.submitFragmentResult({
  worker,
  job,
  fragmentIndex,
  workerToken,
  resultHash,
  proofRef,
  signers: [workerKeypair],
});
```

### 12.5 Verifier download and checksum

A verifier should check the same commitments before voting:

```ts
const storage = await sdk.fetchJobStorage(job);
const fragmentAccount = await sdk.fetchFragment(fragment);

const resultBytes = await p2p.download(resultManifest.output_uri);
assertBytesEqual(sha256Bytes(resultBytes), fragmentAccount.resultHash);

const proofManifestBytes = await p2p.download(resultManifest.proof_uri);
assertBytesEqual(sha256Bytes(proofManifestBytes), fragmentAccount.proofRef);

const valid = await verifyComputation({
  inputBytes,
  resultBytes,
  proofManifestBytes,
});

await sdk.voteFragment({
  verifier,
  job,
  fragment,
  escrow,
  workerToken,
  choice: valid,
  signers: [verifierKeypair],
});
```

### 12.6 Encryption metadata

When inputs are encrypted, `encryptionRefHash` commits to the encryption metadata manifest.

Example:

```json
{
  "version": 1,
  "algorithm": "aes-256-gcm",
  "key_policy": "worker-specific",
  "key_commitment": "...",
  "nonce_commitment": "..."
}
```

The SDK does not manage private keys directly. Key exchange, access control, or threshold decryption should live in the storage/orchestration layer.

---

## 13. Split and sub-fragment helpers

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

## 14. Passive network staking helpers

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

## 15. Account fetch helpers

```ts
const jobData = await sdk.fetchJob(job);
const jobStorageData = await sdk.fetchJobStorage(job);
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

## 16. Event listeners

Listen to one event:

```ts
const sub = sdk.events.on("jobStorageDeclared", (event, slot, signature) => {
  console.log(event.job.toBase58());
  console.log(event.manifestHash);
});
```

Listen to reputation updates:

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
jobStorageDeclared
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

## 17. Typical backend flow

```txt
1. Upload task files and manifest to P2P/off-chain storage.
2. Compute manifest_hash, input_root_hash, storage_ref_hash.
3. Call createJob.
4. Call declareJobStorage.
5. Listen to jobCreated and jobStorageDeclared.
6. Fetch the job and JobStorage accounts.
7. Store the job and storage commitments in the off-chain database.
8. Expose available fragments to workers.
9. Workers call claimFragment.
10. Backend listens to fragmentClaimed.
11. Workers execute computation off-chain.
12. Workers submit resultHash and proofRef.
13. Backend listens to fragmentSubmitted.
14. Verifiers fetch the off-chain result/proof and call voteFragment.
15. Backend listens to fragmentVerified / fragmentRejected.
16. Verifiers claim rewards.
17. When all fragments and verifier rewards are complete, finalizeJob.
18. Backend indexes jobFinalized for users.
```

Recommended indexer table for storage:

```txt
job_storage
- job_storage_pubkey
- job_pubkey
- manifest_hash
- input_root_hash
- storage_ref_hash
- encryption_ref_hash
- declared_by
- created_at_unix
- slot
- signature
```

---

## 18. Typical worker node flow

```txt
1. registerWorker
2. optionally stakeWorker for better/higher-risk tasks
3. read available fragments from backend/indexer
4. fetch JobStorage for the job
5. download storage reference manifest
6. download task manifest
7. verify manifest_hash
8. download assigned fragment input
9. verify input checksum
10. claimFragment
11. compute off-chain
12. upload result/proof off-chain
13. submitFragmentResult(resultHash, proofRef)
14. wait for fragmentVerified or fragmentRejected
15. resubmit if rejected and allowed
```

A worker that calculates well increases `computeReputation`.

---

## 19. Typical verifier node flow

```txt
1. registerWorker
2. optionally stakeWorker for higher-risk verification work
3. listen to fragmentSubmitted
4. fetch JobStorage and Fragment
5. download manifest, input, output and proof metadata
6. verify all checksums against JobStorage and Fragment hashes
7. verify computation
8. voteFragment(true/false)
9. if vote wins, claimVerifierReward
```

A verifier that votes correctly and claims rewards increases `verifyReputation`.

---

## 20. Typical frontend flow

A frontend can use the SDK to:

```txt
1. connect wallet;
2. register user as worker/verifier;
3. show compute / verify / global reputation;
4. show active stake and passive network stake;
5. create jobs;
6. declare job storage commitments;
7. display job and fragment status;
8. display sub-fragment trees;
9. show storage manifest status and checksum status;
10. listen to live events;
11. show final output_uri and final_hash.
```

---

## 21. Hash handling

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

For hex:

```ts
export function sha256Hex(data: Buffer | Uint8Array | string): string {
  const buffer = typeof data === "string" ? Buffer.from(data) : Buffer.from(data);
  return createHash("sha256").update(buffer).digest("hex");
}
```

Do not rely on `hash(uri)` to prove file contents. Use `hash(file_content)` or a canonical manifest containing the URI, content hash, size and MIME type.

Recommended flow:

```txt
manifest bytes       -> manifestHash
all input checksums  -> inputRootHash
storage ref manifest -> storageRefHash
worker output        -> resultHash
proof manifest       -> proofRef
final output         -> finalHash
```

---

## 22. Common errors

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

### Missing JobStorage account

Create and declare job storage after creating the job:

```ts
await sdk.declareJobStorage({
  job,
  manifestHash,
  inputRootHash,
  storageRefHash,
});
```

Then fetch:

```ts
const storage = await sdk.fetchJobStorage(job);
```

### Checksum mismatch

A checksum mismatch means one of these is wrong:

```txt
manifest bytes are not canonicalized the same way
input file differs from the declared checksum
storage ref manifest differs from storage_ref_hash
result/proof file differs from submitted resultHash/proofRef
wrong job or wrong fragment index was used
```

Workers and verifiers should refuse to compute or vote when checksum verification fails.

---

## 23. Production notes

Before production:

- use a dedicated RPC provider;
- avoid hardcoding Program IDs in build artifacts;
- keep IDL and SDK versions aligned;
- add an event indexer;
- store job inputs/outputs/proofs in durable off-chain storage;
- pin or replicate P2P files to avoid unavailable tasks;
- define canonical JSON serialization for manifests;
- audit all slashing and reward logic;
- make split thresholds stricter than local test values;
- increase cooldown and TTL constants;
- keep bootstrap stake low, but restrict high-risk fragments by `requiredStake` and `requiredComputeReputation`;
- add monitoring for `jobStorageDeclared`, `fragmentSubmitted`, and checksum failures.

---

## 24. Validation status

Validated locally:

```txt
registerWorker OK
bootstrap participation without active stake OK
stakeWorker OK
createJob quorum 2 OK
declareJobStorage OK
jobStorageDeclared event OK
fetchJobStorage OK
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

## 25. Milestones

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

The storage layer is compatible with milestones: the task manifest can include milestone metadata, and the layer can later commit to `milestone_root` without storing large files on-chain.
