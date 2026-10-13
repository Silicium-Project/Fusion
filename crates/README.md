# crates/ — runtime Rust

Tout le code qui s'exécute chez un utilisateur ou sur le serveur. Il a
remplacé l'ancien runtime Python, supprimé (voir
[`docs/architecture/rust-migration.md`](../docs/architecture/rust-migration.md)).

| Crate | Paquet Cargo | Produit | Rôle | Maturité |
| --- | --- | --- | --- | --- |
| [`node-core/`](node-core/) | `silicium_node_core` | bibliothèque | Types réseau, journal de tâches signé, réputation, matériel, exécution WASM/OCI | Solide, bien testé |
| [`p2p-node/`](p2p-node/) | `p2p_node` | binaire `p2p_node` | Nœud libp2p, API HTTP locale, workloads (orchestrateur et worker) | Production (canal dev) |
| [`compute-daemon/`](compute-daemon/) | `compute_daemon` | binaire `compute_daemon` | Calcul et vérification locaux (lance le raytracer) | Prototype |
| [`reputation-bridge/`](reputation-bridge/) | `reputation_bridge` | binaire `reputation_bridge` | Scores de réputation, vérification de stake Solana | Prototype |
| [`raytracer/`](raytracer/) | `silicium-raytracer` | binaire `silicium-raytracer` | Moteur de rendu déterministe, utilisé en production | Production |
| [`embedding/`](embedding/) | `silicium-embedding` | bibliothèque + binaire `silicium-embed` | Recherche dans des documents : lecture des documents, passages, modèle épinglé, vecteurs, index | Nouveau (dev) |

Dépendances entre crates : `p2p-node` dépend de `node-core`, du raytracer
(pipeline de tuiles) et de `embedding` (dépendances par chemin). Les autres crates sont indépendantes et communiquent en HTTP local.

## Construire et tester

Toutes les crates font partie d'un **workspace Cargo unique** (`Network/Cargo.toml`) :
un seul `Cargo.lock` versionné, un seul dossier `Network/target/`, des versions de
dépendances partagées (`[workspace.dependencies]`) et des profils communs. Depuis
`Network/` :

```bash
cargo test --workspace --locked
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo fmt --all --check
cargo test -p <paquet>          # une seule crate (nom du paquet, cf. tableau)
```

Les Dockerfiles de `p2p-node` et `reputation-bridge` se construisent avec
`Network/` comme contexte (voir leur `Dockerfile.dockerignore`).
`solana-layer/` reste un workspace Anchor séparé.

## Conventions

- Une crate = une responsabilité. Un fichier source ne devrait pas dépasser
  ~400 lignes : au-delà, découper en modules (`mod api;`, `mod swarm;`…).
- Chaque crate a un `README.md` (rôle, configuration, API, limites connues) et une
  doc de crate (`//!`) en tête de `lib.rs` / `main.rs`.
- Aucun chemin de fichier, image Docker ou variable d'environnement ne doit être
  accepté depuis le réseau sans validation.
- Tout appel réseau ou processus externe a un timeout.
