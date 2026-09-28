# crates/ — runtime Rust

Tout le code Rust qui s'exécute chez un utilisateur ou sur le serveur. C'est le
runtime **cible** : il remplace progressivement le runtime Python de `tools/`,
`networked/` et `workloads/` (voir
[`docs/architecture/rust-migration.md`](../docs/architecture/rust-migration.md)).

| Crate | Paquet Cargo | Produit | Rôle | Maturité |
| --- | --- | --- | --- | --- |
| [`node-core/`](node-core/) | `silicium_node_core` | bibliothèque | Types réseau, journal de tâches signé, réputation, matériel, exécution WASM/OCI | Solide, bien testé |
| [`p2p-node/`](p2p-node/) | `p2p_node` | binaire `p2p_node` | Nœud libp2p + API HTTP locale | Prototype |
| [`compute-daemon/`](compute-daemon/) | `compute_daemon` | binaire `compute_daemon` | Calcul et vérification locaux (lance le raytracer) | Prototype |
| [`reputation-bridge/`](reputation-bridge/) | `reputation_bridge` | binaire `reputation_bridge` | Scores de réputation, vérification de stake Solana | Prototype |
| [`raytracer/`](raytracer/) | `silicium-raytracer` | binaire `silicium-raytracer` | Moteur de rendu déterministe, utilisé en production | Production |

Dépendances entre crates : seul `p2p-node` dépend de `node-core` (dépendance
par chemin). Les autres crates sont indépendantes et communiquent en HTTP local.

## Construire et tester

Chaque crate a pour l'instant son propre `Cargo.toml` :

```bash
cargo test --manifest-path crates/<crate>/Cargo.toml
cargo clippy --manifest-path crates/<crate>/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path crates/<crate>/Cargo.toml --check
```

Étape suivante prévue : un workspace Cargo unique (`Network/Cargo.toml`) avec un
seul `Cargo.lock`, une toolchain épinglée et des profils communs.

## Conventions

- Une crate = une responsabilité. Un fichier source ne devrait pas dépasser
  ~400 lignes : au-delà, découper en modules (`mod api;`, `mod swarm;`…).
- Chaque crate a un `README.md` (rôle, configuration, API, limites connues) et une
  doc de crate (`//!`) en tête de `lib.rs` / `main.rs`.
- Aucun chemin de fichier, image Docker ou variable d'environnement ne doit être
  accepté depuis le réseau sans validation.
- Tout appel réseau ou processus externe a un timeout.
