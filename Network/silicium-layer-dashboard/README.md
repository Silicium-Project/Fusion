# Silicium Layer Dashboard

Interface graphique read-only pour observer le layer Solana/Anchor Silicium sur Devnet.

Ce dashboard ne soumet pas de tache, ne signe aucune transaction et n'affiche pas le
resultat client final. Il sert uniquement a inspecter les comptes on-chain du programme
Silicium deploye sur Devnet.

## Stack

- TypeScript
- React
- Vite
- React Flow
- Recharts
- Anchor + Solana Web3.js

## Installation

Depuis la racine du repo :

```bash
cd silicium-layer-dashboard
yarn install
yarn dev
```

Puis ouvrir :

```txt
http://localhost:5174
```

## Utilisation avec Devnet

1. Dans `solana-layer`, regenerer l'IDL :

```bash
cd solana-layer
anchor build
```

2. Dans le dashboard, charger le fichier :

```txt
solana-layer/target/idl/solana_layer.json
```

3. Verifier les valeurs :

```txt
RPC URL    = https://api.devnet.solana.com
Program ID = AkAFDh9CpGHAoM7gL7zAZxdCJVV6bheBTidZEyZ4BMpA
```

4. Cliquer sur `Charger le Devnet`.

Le dashboard force l'adresse du programme dans l'IDL charge avec le Program ID
Devnet courant. Cela evite de lire par erreur un ancien deploiement conserve
dans une IDL generee avant redeploy.

## Ce que le dashboard affiche

- Jobs
- Fragments et sous-fragments
- Split proposals
- Workers et verifiers
- Reputation V2.5 : compute, verify, global
- Votes
- Staking passif

## Limite actuelle

Le dashboard lit les comptes via `program.account.<account>.all()`.
C'est adapte a Devnet et aux demonstrations.

Pour une production reelle, il faudra ajouter un indexer Node.js/PostgreSQL qui
ecoute les events Anchor et stocke l'historique.
