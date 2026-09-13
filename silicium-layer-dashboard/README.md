# Silicium Layer Dashboard

Interface graphique read-only pour visualiser le layer Solana/Anchor Silicium.

## Stack

- TypeScript
- React
- Vite
- React Flow
- Recharts
- Anchor + Solana Web3.js

## Installation

Le dossier du dashboard est deja present dans le repo; aucun unzip manuel n'est necessaire.

Depuis la racine du repo :

```bash
cd Network/silicium-layer-dashboard
yarn install
yarn dev
```

Puis ouvrir :

```txt
http://localhost:5174
```

## Utilisation avec Devnet

1. Dans `solana-layer`, régénérer l'IDL :

```bash
cd solana-layer
anchor build
```

2. Dans le dashboard, charger le fichier :

```txt
solana-layer/target/idl/solana_layer.json
```

3. Vérifier les valeurs :

```txt
RPC URL    = https://api.devnet.solana.com
Program ID = A9bxX9KwPHFP8S4bMPWVzStpq4uMsC7BU15vw2J6Hnz2
```

4. Cliquer sur `Charger depuis Solana`.

## Ce que le dashboard affiche

- Jobs
- Fragments et sous-fragments
- Split proposals
- Workers et verifiers
- Réputation V2.5 : compute, verify, global
- Votes
- Staking passif
- Timeline mock/demo

## Limite actuelle

Le dashboard lit les comptes via `program.account.<account>.all()`.
C'est bien pour Localnet/Devnet et les démos.

Pour une production réelle, il faudra ajouter un indexer Node.js/PostgreSQL qui écoute les events Anchor et stocke l'historique.
