# reputation-bridge (`reputation_bridge`)

Service HTTP qui tient les scores de réputation des pairs et vérifie un stake
Solana. Déployé en production dans le Compose de Fusion (`deploy/compose`).

## Configuration

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `LISTEN_ADDR` | `0.0.0.0:9091` | Adresse d'écoute |
| `SOLANA_RPC_URL` | `https://api.mainnet-beta.solana.com` | RPC Solana |

## API

| Méthode | Route | Rôle |
| --- | --- | --- |
| `GET` | `/health` | Santé |
| `POST` | `/reputation/score` | Score d'un pair |
| `POST` | `/reputation/observe` | Enregistre un succès / échec pour un pair |
| `POST` | `/solana/verify_stake` | Vérifie qu'un wallet atteint un stake minimal |

Le score combine une mémoire courte et une mémoire longue (deux demi-vies) sur
des distributions Beta (`src/reputation.rs`). Les appels Solana passent par le
JSON-RPC en HTTP (`src/solana_bridge.rs`), sans OpenSSL.

## Tests et conteneur

```bash
cargo test --manifest-path crates/reputation-bridge/Cargo.toml --locked
docker build crates/reputation-bridge
```

## Limites connues

- Scores en mémoire, perdus au redémarrage ; pas d'authentification.
- `verify_stake` compare le **solde SOL** du wallet, pas le staking du programme
  Anchor ; RPC mainnet par défaut.
