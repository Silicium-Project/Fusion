# Silicium SDK

SDK TypeScript aligné sur le programme Anchor `silicium_chain`.

## Structure

- `src/types.ts` : types publics du SDK
- `src/constants.ts` : seeds, rôles, constantes
- `src/utils.ts` : helpers BN / buffers / bytes
- `src/parsers.ts` : parsers des comptes Anchor
- `src/sdk.ts` : classe principale `SiliciumSdk`
- `src/index.ts` : exports

## Points importants

### createJob
Le compte `escrow` est créé côté client avec un `Keypair`, car l'instruction Anchor utilise `init` sans seeds.

### initTreasury
Le compte `treasury` est aussi créé avec un `Keypair`, car ton instruction Anchor utilise `init` sans seeds ni ATA imposée.

### voteFragment
Le SDK résout automatiquement `escrow` depuis le `job`, et `workerToken` depuis le `fragment` si tu ne le fournis pas.

### slashVote
Le SDK récupère `treasury_token_account` depuis `treasury_state` et envoie le bon compte token au programme.

## Exemple rapide

```ts
import { AnchorProvider, Program } from "@coral-xyz/anchor";
import { PublicKey } from "@solana/web3.js";
import { SiliciumSdk } from "./src";
import idl from "./idl/silicium_chain.json";

const provider = AnchorProvider.env();
const programId = new PublicKey("4LHNxzAoaumTaJC5zC8C4tRvR71Gwi48YjLraeuVMLsU");
const program = new Program(idl as any, programId, provider);
const sdk = SiliciumSdk.fromProgram(program, provider);

const { signature, job } = await sdk.createJob({
  mint: new PublicKey("..."),
  clientToken: new PublicKey("..."),
  jobId: 1,
  expectedFragments: 8,
  rewardPerFragment: 1_000,
  deadlineUnix: Math.floor(Date.now() / 1000) + 3600,
  fragmentQuorum: 2,
});
```

## Remarque on-chain
Le SDK est aligné avec ton code Anchor fourni. En revanche, ton programme Rust semble contenir au moins deux problèmes à corriger côté on-chain :

- `Treasury::SPACE` est mal parenthésé / ponctué.
- Dans `SlashVote`, il manque une virgule entre deux `constraint` sur `treasury`.

