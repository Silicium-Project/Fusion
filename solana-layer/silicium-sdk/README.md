# Silicium Solana Layer SDK

SDK TypeScript pour brancher facilement le programme Anchor `solana-layer` au backend, au worker node ou au frontend du projet Silicium.

## Installation locale

Place ce dossier dans ton repo, par exemple :

```bash
Network/solana-layer/sdk
```

Puis depuis le dossier `sdk` :

```bash
yarn install
yarn build
```

Dans ton app, importe le SDK :

```ts
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { SiliciumLayerSdk } from "@silicium/solana-layer-sdk";
import type { SolanaLayer } from "../target/types/solana_layer";

const provider = anchor.AnchorProvider.env();
anchor.setProvider(provider);

const program = anchor.workspace.SolanaLayer as Program<SolanaLayer>;
const sdk = new SiliciumLayerSdk({ provider, program });
```

## Exemple rapide

```ts
await sdk.registerWorker();

await sdk.stakeWorker({
  mint,
  workerToken,
  amount: 1_000_000,
});
```

Créer un job :

```ts
const escrow = anchor.web3.Keypair.generate();

const { job } = await sdk.createJob({
  mint,
  clientToken,
  escrow,
  jobId: 1,
  expectedFragments: 2,
  rewardPerFragment: 1_000_000,
  verifierRewardPerVote: 100_000,
  verifierRewardBudget: 1_000_000,
  deadlineUnix: Math.floor(Date.now() / 1000) + 3600,
  fragmentQuorum: 2,
});
```

Claim + submit :

```ts
const { fragment } = await sdk.claimFragment({
  job,
  fragmentIndex: 0,
  workerToken,
});

await sdk.submitFragmentResult({
  job,
  fragmentIndex: 0,
  workerToken,
  resultHash: Array(32).fill(1),
  proofRef: Array(32).fill(2),
});
```

Écouter les events :

```ts
const sub = sdk.events.on("fragmentVerified", (event, slot, signature) => {
  console.log("fragment verified", event, slot, signature);
});

await sub.remove();
```

Écouter tous les events :

```ts
const subs = sdk.events.onAll((name, event, slot, signature) => {
  console.log(name, event, slot, signature);
});
```

## Events supportés

Le SDK écoute les noms Anchor en camelCase :

- `jobCreated`
- `workerRegistered`
- `workerStaked`
- `treasuryInitialized`
- `fragmentClaimed`
- `fragmentReclaimed`
- `fragmentSubmitted`
- `fragmentVerified`
- `fragmentRejected`
- `verifierRewardClaimed`
- `jobFinalized`
- `jobCancelled`
- `voteSlashed`

## Fonctions incluses

- `registerWorker`
- `stakeWorker`
- `createJob`
- `claimFragment`
- `reclaimFragment`
- `submitFragmentResult`
- `resubmitFragmentResult`
- `voteFragment`
- `claimVerifierReward`
- `finalizeJob`
- `cancelJob`
- `initTreasury`
- `slashVote`
- helpers PDA dans `sdk.pdas.*`
- fetch helpers : `fetchJob`, `fetchFragment`, `fetchWorker`, `fetchVote`, `fetchRoundResolution`, `fetchResult`

## Note importante

Ce SDK suppose que ton IDL Anchor est à jour après ajout des events et après rebuild :

```bash
anchor build
```

Si les events `WorkerRegistered`, `WorkerStaked`, `TreasuryInitialized`, `FragmentClaimed`, `FragmentReclaimed` ou le champ `isResubmission` de `fragmentSubmitted` ne remontent pas, rebuild le programme et vérifie que l'IDL généré contient bien ces events.
