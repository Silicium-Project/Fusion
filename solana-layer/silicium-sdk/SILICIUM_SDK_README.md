# Silicium Solana Layer SDK

TypeScript SDK for interacting with the Silicium Solana Layer Anchor program.

The SDK wraps the Anchor program instructions, PDA derivation helpers, account fetch helpers, and program event listeners so the rest of the Silicium backend, frontend, worker nodes, verifier nodes, and off-chain orchestration services can interact with the Solana layer without manually rebuilding every Anchor transaction.

This SDK is the bridge between:

- the on-chain Solana program;
- the off-chain Silicium backend;
- worker nodes;
- verifier nodes;
- frontend dashboards;
- future indexers and orchestration services.

---

## What this SDK does

The SDK provides a clean TypeScript interface for the on-chain Silicium workflow:

- Register compute/verifier workers.
- Stake SPL tokens for workers.
- Create distributed computation jobs.
- Claim fragments.
- Reclaim expired fragments.
- Submit and resubmit fragment results.
- Vote on fragment validity.
- Claim verifier rewards.
- Finalize jobs.
- Cancel jobs.
- Initialize the treasury.
- Slash wrong verifier votes.
- Initialize the network staking pool.
- Stake tokens into the network pool.
- Fund network staking rewards.
- Claim network staking rewards.
- Request unstake from the network pool.
- Withdraw unstaked tokens after cooldown.
- Fetch all important on-chain accounts.
- Listen to all program events.

Main class:

```ts
SiliciumLayerSdk
```

Main entrypoint:

```ts
import { SiliciumLayerSdk } from "./src";
```

---

## Recommended project structure

The SDK is expected to live inside the Anchor project root:

```txt
solana-layer/
├── Anchor.toml
├── programs/
│   └── solana-layer/
├── scripts/
│   └── dev-local-sdk.sh
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
    │   ├── test-sdk.ts
    │   ├── listen-events.ts
    │   └── full-flow.ts
    ├── package.json
    ├── tsconfig.json
    └── README.md
```

This location is recommended because the SDK depends on the Anchor workspace, the generated IDL, and the deployed local program.

---

## Requirements

- Node.js
- npm or Yarn
- Solana CLI
- Anchor CLI
- A built and deployed `solana-layer` Anchor program
- A local wallet configured for Anchor

Install dependencies from the SDK folder:

```bash
cd /home/thomas/eip/Network/solana-layer/silicium-sdk
npm install
```

or:

```bash
yarn install
```

Build the SDK:

```bash
npm run build
```

or:

```bash
yarn build
```

---

## Anchor setup

Before using the SDK, build the Anchor program from the project root:

```bash
cd /home/thomas/eip/Network/solana-layer
anchor keys sync
anchor build
```

`anchor keys sync` is recommended before `anchor build` because it makes sure the `declare_id!(...)` in the Rust program matches the local program keypair.

For local testing, run a local validator and deploy the program:

```bash
solana-test-validator --reset
```

Then in another terminal:

```bash
cd /home/thomas/eip/Network/solana-layer

export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899

solana config set --url localhost
solana airdrop 10

anchor keys sync
anchor build
anchor deploy
```

Anchor may show:

```txt
Warning: 'anchor deploy' is deprecated. Use 'anchor program deploy' instead.
```

For local development, `anchor deploy` still works, but `anchor program deploy` can also be used.

Set the local Anchor environment variables:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

If the wallet does not exist yet:

```bash
solana-keygen new --outfile ~/.config/solana/id.json
```

Airdrop local SOL:

```bash
solana airdrop 10 --url http://127.0.0.1:8899
```

---

## One-command local SDK test

The project includes a helper script:

```bash
scripts/dev-local-sdk.sh
```

Run it from the Anchor project root:

```bash
cd /home/thomas/eip/Network/solana-layer
./scripts/dev-local-sdk.sh
```

The script does the full local setup:

```txt
1. Starts solana-test-validator --reset.
2. Configures Solana localnet.
3. Airdrops SOL to the local wallet.
4. Runs anchor keys sync.
5. Builds the Anchor program.
6. Deploys the Anchor program.
7. Installs SDK dependencies if needed.
8. Runs silicium-sdk/examples/full-flow.ts.
9. Stops the local validator when finished.
```

The script should be launched from the Anchor project root:

```txt
/home/thomas/eip/Network/solana-layer
```

not from inside `silicium-sdk/`.

---

## Included examples

### `test-sdk.ts`

Minimal connection test.

It checks that the SDK can:

- load the Anchor provider;
- load the Solana program;
- derive the worker PDA;
- register a worker if it does not already exist;
- fetch the worker account.

Run:

```bash
cd /home/thomas/eip/Network/solana-layer

export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899

npx ts-node silicium-sdk/examples/test-sdk.ts
```

Expected result:

```txt
SDK loaded
Wallet: <wallet public key>
Program: <program id>
Expected worker PDA: <worker PDA>
Worker data: ...
```

---

### `listen-events.ts`

Event listener for the Solana layer.

It subscribes to all supported Anchor events through:

```ts
sdk.events.onAll(...)
```

Run it in one terminal:

```bash
cd /home/thomas/eip/Network/solana-layer

export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899

npx ts-node silicium-sdk/examples/listen-events.ts
```

Then trigger transactions from another terminal, for example:

```bash
npx ts-node silicium-sdk/examples/test-sdk.ts
```

You should see logs like:

```txt
================ EVENT ================
name: workerRegistered
slot: ...
signature: ...
...
=======================================
```

This file is the recommended starting point for a future backend indexer.

---

### `full-flow.ts`

Complete local integration flow.

It validates the main Solana layer workflow:

```txt
register compute worker
register verifier 1
register verifier 2
stake compute worker
stake verifier 1
stake verifier 2
create job
claim fragment
submit fragment result
vote verifier 1
vote verifier 2
fragment verified
claim verifier 1 reward
claim verifier 2 reward
finalize job
init staking pool
stake network
fund staking rewards
claim staking reward
request unstake
withdraw unstaked if cooldown allows it
fetch final on-chain accounts
```

Run:

```bash
cd /home/thomas/eip/Network/solana-layer
./scripts/dev-local-sdk.sh
```

or, if localnet is already running and the program is deployed:

```bash
cd /home/thomas/eip/Network/solana-layer

export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899

npx ts-node silicium-sdk/examples/full-flow.ts
```

Important local test amounts used by the full flow:

```txt
job reward per fragment: 1_000_000
verifier reward per vote: 100_000
fragment quorum: 2
network stake amount: 1_000_000
```

These values are intentionally high enough to pass the on-chain minimum deposit and minimum staking checks in local tests.

---

## SDK initialization

The SDK is initialized from an Anchor provider and an Anchor program instance:

```ts
const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer;
const sdk = SiliciumLayerSdk.fromWorkspace(provider, program);
```

The SDK stores:

```ts
sdk.provider
sdk.program
sdk.programId
sdk.events
sdk.pdas
```

The connected wallet can be accessed with:

```ts
const wallet = sdk.walletPubkey();
```

---

## PDA helpers

The SDK exposes PDA helpers through `sdk.pdas`:

```ts
const job = sdk.pdas.job(client, jobId);
const fragment = sdk.pdas.fragment(job, fragmentIndex);
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

These helpers should be used by the backend/frontend instead of manually deriving addresses everywhere.

---

## Main instructions

### Register a worker

Registers a wallet as a worker with compute and verify roles.

```ts
const sig = await sdk.registerWorker();
```

Or register another signer:

```ts
await sdk.registerWorker({
  worker: workerKeypair.publicKey,
  signers: [workerKeypair],
});
```

Fetch the worker account:

```ts
const workerAccount = sdk.pdas.worker(wallet.publicKey);
const worker = await sdk.fetchWorker(workerAccount, true);
```

You can also fetch by owner wallet directly:

```ts
const worker = await sdk.fetchWorker(wallet.publicKey);
```

Important: if you already pass the worker PDA, use:

```ts
await sdk.fetchWorker(workerAccount, true);
```

---

### Stake worker tokens

Stakes SPL tokens for a registered worker.

```ts
await sdk.stakeWorker({
  mint,
  workerToken,
  amount: 1_000_000,
});
```

Or stake for another signer:

```ts
await sdk.stakeWorker({
  worker: workerKeypair.publicKey,
  workerToken,
  mint,
  amount: 1_000_000,
  signers: [workerKeypair],
});
```

The SDK derives:

- worker account PDA;
- stake authority PDA;
- stake vault PDA.

---

### Create a job

Creates a distributed computation job and funds the escrow.

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

The SDK returns useful addresses:

```ts
created.signature
created.job
```

The SDK derives:

- job PDA;
- escrow authority PDA.

The total escrow deposit is:

```txt
expectedFragments * rewardPerFragment + verifierRewardBudget
```

Make sure this amount is greater than the on-chain `MIN_JOB_DEPOSIT`.

---

### Claim a fragment

Claims an available fragment for a worker.

```ts
const claimed = await sdk.claimFragment({
  worker: computeWorker.publicKey,
  job,
  fragmentIndex: 0,
  workerToken,
  signers: [computeWorker],
});
```

The SDK returns:

```ts
claimed.signature
claimed.fragment
```

The SDK derives:

- fragment PDA;
- worker account PDA.

---

### Reclaim an expired fragment

Makes an expired claimed fragment available again.

```ts
await sdk.reclaimFragment({
  job,
  fragmentIndex: 0,
});
```

This is useful for backend schedulers that detect abandoned work.

---

### Submit a fragment result

Submits a result hash and proof reference for a claimed fragment.

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

`resultHash` and `proofRef` must be 32-byte values.

Example:

```ts
const resultHash = new Uint8Array(32);
const proofRef = new Uint8Array(32);
```

---

### Resubmit a rejected fragment result

Resubmits a result after the previous one was rejected.

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

The emitted `fragmentSubmitted` event includes:

```ts
isResubmission: true
```

---

### Vote on a fragment

A verifier votes on a submitted fragment.

```ts
const voteResult = await sdk.voteFragment({
  verifier: verifier.publicKey,
  job,
  fragment,
  escrow,
  workerToken,
  choice: true,
  signers: [verifier],
});
```

The vote can trigger one of two outcomes depending on quorum:

- `fragmentVerified`
- `fragmentRejected`

For the local full flow, `fragmentQuorum` is set to `2`, so two verifiers must vote `true` before the fragment is verified.

---

### Claim verifier reward

Claims the verifier reward for an eligible vote.

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

A verifier can only claim if the vote is part of the winning resolution.

---

### Finalize a job

Finalizes a job once all fragments are verified and eligible verifier rewards have been claimed.

```ts
const finalized = await sdk.finalizeJob({
  job,
  escrow,
  clientToken,
  finalHash,
  outputUri: "ipfs://silicium-output",
});
```

The SDK returns:

```ts
finalized.signature
finalized.result
```

The SDK derives the job result PDA.

---

### Cancel a job

Cancels a job and refunds the remaining escrow amount to the client.

```ts
await sdk.cancelJob({
  job,
  escrow,
  clientToken,
});
```

---

### Initialize treasury

Initializes the treasury accounts for a mint.

```ts
await sdk.initTreasury({
  mint,
  treasury,
});
```

The SDK derives:

- treasury state PDA;
- treasury authority PDA.

---

### Slash a wrong vote

Slashes a verifier for a wrong vote.

```ts
await sdk.slashVote({
  job,
  fragment,
  vote,
  verifierWorker,
  verifierStakeVault,
  treasuryState,
  treasury,
});
```

---

## Network staking instructions

The SDK also exposes the network-level staking flow.

This is different from worker staking:

- worker staking secures compute/verifier behavior;
- network staking participates in the staking pool and can receive staking rewards.

---

### Initialize staking pool

```ts
const stakeVault = Keypair.generate();
const rewardVault = Keypair.generate();

const poolCreated = await sdk.initStakingPool({
  mint,
  stakeVault,
  rewardVault,
});
```

The SDK returns:

```ts
poolCreated.signature
poolCreated.pool
```

---

### Stake into the network pool

```ts
await sdk.stakeNetwork({
  mint,
  ownerToken,
  amount: 1_000_000,
});
```

The amount must be greater than or equal to the on-chain `MIN_NETWORK_STAKE`.

For local tests, `1_000_000` is recommended.

---

### Fund staking rewards

```ts
await sdk.fundStakingRewards({
  mint,
  funderToken,
  amount: 100_000,
});
```

---

### Claim staking reward

```ts
await sdk.claimStakingReward({
  mint,
  ownerRewardToken,
});
```

---

### Request unstake

```ts
await sdk.requestUnstake({
  mint,
  amount: 500_000,
});
```

---

### Withdraw unstaked tokens

```ts
await sdk.withdrawUnstaked({
  mint,
  ownerToken,
});
```

This may fail if the unstake cooldown is still active.

For local tests, either wait for the cooldown or reduce `UNSTAKE_COOLDOWN_SECS` in the on-chain program.

---

## Account fetch helpers

The SDK exposes helpers to fetch Anchor accounts:

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
```

`fetchWorker` has two modes:

```ts
await sdk.fetchWorker(workerOwnerPublicKey);
await sdk.fetchWorker(workerAccountPda, true);
```

Use the second form when you already derived the worker PDA.

---

## Event listeners

The SDK wraps Anchor event listeners with `sdk.events`.

Listen to one event:

```ts
const sub = sdk.events.on("workerRegistered", (event, slot, signature) => {
  console.log("workerRegistered", event, slot, signature);
});
```

Remove a listener:

```ts
await sub.remove();
```

Listen to all events:

```ts
const subscriptions = sdk.events.onAll((name, event, slot, signature) => {
  console.log("event", name, event, slot, signature);
});
```

Remove all listeners:

```ts
await Promise.all(subscriptions.map((sub) => sub.remove()));
```

Supported events:

```txt
jobCreated
workerRegistered
workerStaked
workerReputationUpdated
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
stakingPoolInitialized
networkStakeDeposited
stakingRewardsFunded
stakingRewardClaimed
networkUnstakeRequested
networkUnstakeWithdrawn
```

The current SDK listens to 20 program events through `onAll()`.

---

## Typical backend flow

A backend service can use the SDK like this:

```txt
1. Listen to jobCreated.
2. Fetch the job account.
3. Store the job in the off-chain database.
4. Assign or expose available fragments.
5. Workers call claimFragment.
6. Backend listens to fragmentClaimed.
7. Workers execute the real computation off-chain.
8. Workers submit resultHash and proofRef with submitFragmentResult.
9. Backend listens to fragmentSubmitted.
10. Verifiers fetch the result/proof off-chain and vote with voteFragment.
11. Backend listens to fragmentVerified / fragmentRejected.
12. Verifiers claim rewards with claimVerifierReward.
13. Once all fragments are verified and rewards are claimed, call finalizeJob.
14. Backend indexes jobFinalized for frontend/API users.
```

The event system lets your backend avoid constant polling while still keeping an indexed database in sync with the Solana layer.

---

## Typical worker node flow

A worker node can use the SDK like this:

```txt
1. Register itself with registerWorker.
2. Stake SPL tokens with stakeWorker.
3. Listen for available jobs from the backend/indexer.
4. Claim a fragment with claimFragment.
5. Execute the computation off-chain.
6. Store output/proof off-chain.
7. Submit resultHash and proofRef with submitFragmentResult.
8. Wait for fragmentVerified or fragmentRejected.
9. If rejected and allowed, resubmit with resubmitFragmentResult.
```

---

## Typical verifier node flow

A verifier node can use the SDK like this:

```txt
1. Register itself with registerWorker.
2. Stake SPL tokens with stakeWorker.
3. Listen to fragmentSubmitted events.
4. Fetch the off-chain result/proof using proofRef.
5. Verify the computation off-chain.
6. Vote with voteFragment.
7. If the vote is part of the winning outcome, call claimVerifierReward.
```

---

## Typical frontend flow

A frontend can use the SDK to:

```txt
1. Connect a wallet.
2. Register the wallet as a worker.
3. Show worker status, reputation and stake amount.
4. Let a client create a job.
5. Display job and fragment state.
6. Subscribe to live program events.
7. Display staking pool and network staking state.
```

For production frontend use, the SDK should be bundled with the generated IDL or initialized with an Anchor `Program` created from the IDL.

---

## Local testing checklist

From the Anchor project root:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

Run the full local flow:

```bash
./scripts/dev-local-sdk.sh
```

Or run steps manually:

```bash
solana-test-validator --reset
```

In another terminal:

```bash
cd /home/thomas/eip/Network/solana-layer

export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899

solana config set --url localhost
solana airdrop 10
anchor keys sync
anchor build
anchor deploy

npx ts-node silicium-sdk/examples/full-flow.ts
```

Run only the connection test:

```bash
npx ts-node silicium-sdk/examples/test-sdk.ts
```

Run only the event listener:

```bash
npx ts-node silicium-sdk/examples/listen-events.ts
```

---

## Common errors

### `expected environment variable ANCHOR_WALLET is not set`

Set:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
```

Also set:

```bash
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

---

### `anchor.workspace.SolanaLayer is undefined`

Run the script from the Anchor project root, not from inside the SDK folder:

```bash
cd /home/thomas/eip/Network/solana-layer
npx ts-node silicium-sdk/examples/test-sdk.ts
```

---

### Program ID mismatch

Example:

```txt
Program ID mismatch detected for program 'solana_layer'
Keypair file has: <program id A>
Source code has:  <program id B>
```

Fix from the Anchor project root:

```bash
cd /home/thomas/eip/Network/solana-layer
anchor keys sync
anchor build
```

Verify:

```bash
anchor keys list
grep -R "declare_id" programs/solana-layer/src/lib.rs
```

The program ID used by the SDK must match the deployed program ID.

---

### `Account does not exist or has no data`

Make sure you are fetching the correct PDA.

For workers:

```ts
await sdk.fetchWorker(wallet.publicKey);
```

or:

```ts
const workerAccount = sdk.pdas.worker(wallet.publicKey);
await sdk.fetchWorker(workerAccount, true);
```

Do not pass a worker PDA without the second argument `true`, otherwise the SDK will derive a PDA from the PDA and fetch the wrong address.

---

### `InvalidParams` in `create_job.rs`

This usually means one of the job parameters is below an on-chain minimum.

Common causes:

```txt
fragmentQuorum too low
expectedFragments invalid
deadline too short or invalid
verifierRewardBudget inconsistent
```

For local full-flow tests, use:

```ts
const expectedFragments = 1;
const rewardPerFragment = 1_000_000;
const verifierRewardPerVote = 100_000;
const fragmentQuorum = 2;
const verifierRewardBudget = expectedFragments * fragmentQuorum * verifierRewardPerVote;
```

---

### `DepositTooSmall` in `create_job.rs`

The total job deposit is below the on-chain minimum.

The deposit is:

```txt
expectedFragments * rewardPerFragment + verifierRewardBudget
```

Use larger test values, for example:

```ts
const rewardPerFragment = 1_000_000;
const verifierRewardPerVote = 100_000;
const fragmentQuorum = 2;
const verifierRewardBudget = 200_000;
```

Make sure the client token account has enough tokens.

---

### `InvalidAmount` in `stake_network.rs`

The network stake amount is below the on-chain `MIN_NETWORK_STAKE`.

Use a larger amount in local tests:

```ts
await sdk.stakeNetwork({
  mint,
  ownerToken: clientToken,
  amount: 1_000_000,
});
```

---

### `withdrawUnstaked` fails

The unstake cooldown is probably still active.

This is expected in local tests unless you wait for the cooldown or reduce the cooldown constant in the on-chain program.

---

### `Type instantiation is excessively deep and possibly infinite`

This is a TypeScript/Anchor typing issue. The SDK avoids it internally by casting Anchor `methods` and `account` namespaces where needed.

---

## Notes for production

Before using this SDK in production, consider:

- Replace test TTL values in the on-chain program with production values.
- Use stricter generated Anchor types instead of `any` where possible.
- Add integration tests for every SDK method.
- Add retry/confirmation helpers around important transactions.
- Add structured error mapping for Anchor errors.
- Add backend indexing for all events.
- Store off-chain job inputs, outputs and proofs in a durable storage layer.
- Validate `proofRef` and `resultHash` consistently across worker/verifier nodes.
- Pin package versions for Anchor, Solana Web3, and SPL Token.
- Avoid hardcoding program IDs in production builds.
- Keep the SDK program ID aligned with `anchor keys list` and `declare_id!(...)`.

---

## Current local validation status

The following flow has been validated locally through the SDK:

```txt
SDK initialization OK
Anchor event listener OK
registerWorker OK
stakeWorker OK
createJob OK
claimFragment OK
submitFragmentResult OK
voteFragment with quorum 2 OK
fragmentVerified OK
claimVerifierReward OK
finalizeJob OK
initStakingPool OK
stakeNetwork OK
fundStakingRewards OK
claimStakingReward OK
requestUnstake OK
```

`withdrawUnstaked` depends on the unstake cooldown and may require waiting or lowering the cooldown for local tests.

---

## License

Internal project SDK for the Silicium Solana Layer.
