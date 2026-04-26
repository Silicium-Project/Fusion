# Silicium Solana Layer SDK

TypeScript SDK for interacting with the Silicium Solana Layer Anchor program.

The SDK wraps the Anchor program instructions, PDA derivation helpers, account fetch helpers, and program event listeners so the rest of the Silicium backend/frontend can interact with the Solana layer without manually rebuilding every Anchor transaction.

---

## What this SDK does

The SDK provides a clean TypeScript interface for the on-chain Silicium workflow:

- Register compute/verifier workers.
- Stake SPL tokens for workers.
- Create distributed computation jobs.
- Claim fragments.
- Submit and resubmit fragment results.
- Vote on fragment validity.
- Claim verifier rewards.
- Finalize jobs.
- Cancel jobs.
- Initialize the treasury.
- Slash wrong verifier votes.
- Fetch on-chain accounts.
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
├── target/
│   ├── idl/
│   │   └── solana_layer.json
│   └── types/
│       └── solana_layer.ts
├── tests/
└── silicium-sdk/
    ├── src/
    ├── examples/
    ├── package.json
    └── tsconfig.json
```

This location is recommended because the SDK depends on the Anchor workspace, the generated IDL, and the deployed local program.

---

## Requirements

- Node.js
- Yarn
- Solana CLI
- Anchor CLI
- A built and deployed `solana-layer` Anchor program
- A local wallet configured for Anchor

Install dependencies from the SDK folder:

```bash
cd /home/thomas/eip/Network/solana-layer/silicium-sdk
yarn install
```

Build the SDK:

```bash
yarn build
```

---

## Anchor setup

Before using the SDK, build the Anchor program from the project root:

```bash
cd /home/thomas/eip/Network/solana-layer
anchor build
```

For local testing, run a local validator and deploy the program.

Option 1, with Anchor:

```bash
anchor test --detach --run "echo validator ready"
```

Option 2, manually:

```bash
solana-test-validator --reset
```

Then in another terminal:

```bash
cd /home/thomas/eip/Network/solana-layer
anchor build
anchor deploy --provider.cluster localnet
```

Set the local Anchor environment variables:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

If the wallet does not exist yet:

```bash
solana-keygen new -o ~/.config/solana/id.json
```

Airdrop local SOL:

```bash
solana airdrop 10 ~/.config/solana/id.json --url http://127.0.0.1:8899
```

---

## Basic usage

Create `silicium-sdk/examples/test-sdk.ts`:

```ts
import * as anchor from "@coral-xyz/anchor";
import { Connection } from "@solana/web3.js";
import { SiliciumLayerSdk } from "../src";

async function main() {
  const connection = new Connection("http://127.0.0.1:8899", "confirmed");

  const wallet = anchor.Wallet.local();

  const provider = new anchor.AnchorProvider(connection, wallet, {
    commitment: "confirmed",
    preflightCommitment: "confirmed",
  });

  anchor.setProvider(provider);

  const program = anchor.workspace.SolanaLayer;
  const sdk = SiliciumLayerSdk.fromWorkspace(provider, program);

  console.log("SDK loaded");
  console.log("Wallet:", wallet.publicKey.toBase58());
  console.log("Program:", sdk.programId.toBase58());

  const workerAccount = sdk.pdas.worker(wallet.publicKey);

  console.log("Expected worker PDA:", workerAccount.toBase58());

  const existingWorker = await provider.connection.getAccountInfo(workerAccount, "confirmed");

  if (!existingWorker) {
    const sig = await sdk.registerWorker();
    console.log("Worker registered tx:", sig);
    await provider.connection.confirmTransaction(sig, "confirmed");
  }

  const worker = await sdk.fetchWorker(workerAccount, true);

  console.log("Worker account:", workerAccount.toBase58());
  console.log("Worker data:", worker);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

Run it from the Anchor project root:

```bash
cd /home/thomas/eip/Network/solana-layer
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

## SDK initialization

The SDK is initialized from an Anchor provider and an Anchor program instance:

```ts
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
```

These helpers should be used by the backend/frontend instead of manually deriving addresses everywhere.

---

## Main instructions

### Register a worker

Registers the connected wallet as a worker with compute and verify roles.

```ts
const sig = await sdk.registerWorker();
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

The SDK derives:

- worker account PDA
- stake authority PDA
- stake vault PDA

---

### Create a job

Creates a distributed computation job and funds the escrow.

```ts
await sdk.createJob({
  jobId,
  expectedFragments: 2,
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

The SDK derives:

- job PDA
- escrow authority PDA

---

### Claim a fragment

Claims an available fragment for the connected worker.

```ts
await sdk.claimFragment({
  job,
  fragmentIndex: 0,
  workerToken,
});
```

The SDK derives:

- fragment PDA
- worker account PDA

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
  job,
  fragmentIndex: 0,
  workerToken,
  resultHash,
  proofRef,
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
  job,
  fragmentIndex: 0,
  workerToken,
  resultHash,
  proofRef,
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
await sdk.voteFragment({
  job,
  fragment,
  fragmentIndex: 0,
  approve: true,
  verifierToken,
  workerToken,
  escrow,
});
```

The vote can trigger one of two outcomes depending on quorum:

- `fragmentVerified`
- `fragmentRejected`

---

### Claim verifier reward

Claims the verifier reward for an eligible vote.

```ts
await sdk.claimVerifierReward({
  job,
  fragment,
  vote,
  escrow,
  verifierToken,
});
```

---

### Finalize a job

Finalizes a job once all fragments are verified.

```ts
await sdk.finalizeJob({
  job,
  escrow,
  clientToken,
  finalHash,
});
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

- treasury state PDA
- treasury authority PDA

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
```

---

## Typical backend flow

A backend service can use the SDK like this:

```txt
1. Listen to jobCreated.
2. Fetch the job account.
3. Assign or expose available fragments.
4. Workers call claimFragment.
5. Workers submit results with submitFragmentResult.
6. Verifiers vote with voteFragment.
7. Backend listens to fragmentVerified / fragmentRejected.
8. Once all fragments are verified, call finalizeJob.
9. Index jobFinalized for frontend/API users.
```

The event system lets your backend avoid constant polling while still keeping an indexed database in sync with the Solana layer.

---

## Typical frontend flow

A frontend can use the SDK to:

```txt
1. Connect a wallet.
2. Register the wallet as a worker.
3. Show worker status and stake amount.
4. Let a client create a job.
5. Display job and fragment state.
6. Subscribe to live program events.
```

For production frontend use, the SDK should be bundled with the generated IDL or initialized with an Anchor `Program` created from the IDL.

---

## Local testing checklist

From the Anchor project root:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
export ANCHOR_PROVIDER_URL=http://127.0.0.1:8899
```

Start localnet and deploy:

```bash
anchor test --detach --run "echo validator ready"
```

Run the SDK example:

```bash
npx ts-node silicium-sdk/examples/test-sdk.ts
```

If a worker was already registered, the script should fetch it instead of trying to recreate it.

---

## Common errors

### `expected environment variable ANCHOR_WALLET is not set`

Set:

```bash
export ANCHOR_WALLET=~/.config/solana/id.json
```

### `anchor.workspace.SolanaLayer is undefined`

Run the script from the Anchor project root, not from inside the SDK folder:

```bash
cd /home/thomas/eip/Network/solana-layer
npx ts-node silicium-sdk/examples/test-sdk.ts
```

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
- Pin package versions for Anchor, Solana Web3, and SPL Token.
- Avoid hardcoding program IDs in production builds.

---

## License

Internal project SDK for the Silicium Solana Layer.
