# Silicium Network

Réseau de calcul distribué de Silicium : des nœuds installés chez des
particuliers reçoivent des fragments de travail, les calculent, les font
vérifier par d'autres nœuds, puis le résultat est réassemblé. La couche
Solana assure la transparence (jobs, réputation, staking, récompenses).

## État actuel en une phrase

Le runtime réseau **en production est encore en Python** (`tools/network_node.py`).
Le runtime **cible est en Rust** (`crates/`) et le remplace progressivement.
Règle du projet : *Rust pour tout ce qui s'exécute chez un utilisateur ou sur
le serveur, Python uniquement pour l'outillage des développeurs.*

Le plan de migration est décrit dans
[`docs/architecture/rust-migration.md`](docs/architecture/rust-migration.md).

## Carte du dépôt

| Dossier | Langage | Rôle | Statut |
| --- | --- | --- | --- |
| [`crates/`](crates/) | Rust | Nœud P2P, cœur du nœud, daemon de calcul, pont de réputation, raytracer | Cible ; nœud P2P encore prototype |
| [`solana-layer/`](solana-layer/) | Rust (Anchor) + TypeScript | Programme on-chain, SDK, tests Anchor | Actif |
| [`silicium-layer-dashboard/`](silicium-layer-dashboard/) | TypeScript (Vite) | Tableau de bord réseau / Solana | Actif |
| [`tools/`](tools/) | Python | Runtime Python de production (nœud, RPC, télémétrie, transport, API MCP) | **Legacy** — à remplacer par `crates/` |
| [`networked/`](networked/) | Python | Paquet `networked` (blobs de contenu partagés par le runtime) | **Legacy** |
| [`workloads/`](workloads/) | YAML + Python | Tous les workloads : manifestes, registre, handlers, fixtures, golden data | Actif ; handlers Python **legacy** (le rendu est dans `crates/raytracer`) |
| [`tools/dev/`](tools/dev/) | Python | Outillage développeur : E2E, démo « world », contrôles qualité, release, TUI | Outil dev (reste en Python) |
| [`tests/`](tests/) | Python | Tests pytest du runtime Python et des outils | Actif |
| [`proto/`](proto/) | Protobuf | Contrat RPC du runtime Python | Legacy |
| [`i18n/`](i18n/) | JSON / shell | Traductions de la CLI et des scripts | Actif |
| [`infra/`](infra/) | Docker, systemd | Conteneurs locaux (Solana, bootstrap, world), unités systemd | Actif |
| [`ci/`](ci/) | Shell | Contrôles CI, E2E Docker, smoke Kademlia | Actif |
| [`docs/`](docs/) | Markdown | Documentation technique, rangée par partie | — |
| `silicium` | Python | CLI développeur et lanceur du nœud (code : [`tools/cli/`](tools/cli/)) | Actif |

Chaque dossier contient un `README.md` qui détaille son contenu.

## Démarrage rapide (développement)

```bash
# Dépendances Python des outils et tests
python3 -m pip install -r requirements-dev.txt

# Tests Python
python3 -m pytest

# Tests Rust (workspace Cargo unique : Cargo.toml + Cargo.lock à la racine)
cargo test --workspace --locked
make rust-lint        # cargo fmt --check + clippy -D warnings

# Contrôle rapide utilisé par la CI
make check
```

Le détail des prérequis et des contrôles est dans
[`docs/development/core-stability.md`](docs/development/core-stability.md).

## Documentation

L'index complet est dans [`docs/README.md`](docs/README.md).

## Licence et sécurité

Voir [`LICENSE`](LICENSE) et [`SECURITY.md`](SECURITY.md).
