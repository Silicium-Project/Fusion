# Silicium Network

Réseau de calcul distribué de Silicium : des nœuds installés chez des
particuliers reçoivent des fragments de travail, les calculent, les font
vérifier par d'autres nœuds, puis le résultat est réassemblé. La couche
Solana assure la transparence (jobs, réputation, staking, récompenses).

## État actuel en une phrase

Le runtime réseau est **entièrement en Rust** (`crates/`) : le même binaire
`p2p_node` sert d'orchestrateur sur le serveur et de worker chez les
utilisateurs. Règle du projet : *Rust pour tout ce qui s'exécute chez un
utilisateur ou sur le serveur, Python uniquement pour l'outillage des
développeurs.* L'ancien runtime Python a été supprimé
([`docs/architecture/rust-migration.md`](docs/architecture/rust-migration.md)).

## Carte du dépôt

| Dossier | Langage | Rôle |
| --- | --- | --- |
| [`crates/`](crates/) | Rust | Nœud P2P et workloads, cœur du nœud, daemon de calcul, pont de réputation, raytracer, embeddings |
| [`solana-layer/`](solana-layer/) | Rust (Anchor) + TypeScript | Programme on-chain, SDK, tests Anchor |
| [`tools/dev/`](tools/dev/) | Python | Outillage développeur : contrôles qualité, preflight Solana |
| [`tests/`](tests/) | Python | Tests pytest de l'outillage développeur |
| [`i18n/`](i18n/) | JSON / shell | Traductions des scripts d'infra |
| [`infra/`](infra/) | Docker | Validateur Solana local, proxy, nœud d'amorçage |
| [`ci/`](ci/) | Shell | Contrôle principal, e2e réseau, smoke Kademlia, réparation des runners |
| [`docs/`](docs/) | Markdown | Documentation technique, rangée par partie |

Chaque dossier contient un `README.md` qui détaille son contenu.

## Démarrage rapide (développement)

```bash
# Tests Rust (workspace Cargo unique : Cargo.toml + Cargo.lock à la racine)
cargo test --workspace --locked
make rust-lint        # cargo fmt --check + clippy -D warnings

# Réseau complet en local (orchestrateur + workers, sans Docker)
make e2e

# Tests de l'outillage Python
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q

# Contrôle rapide utilisé par la CI de Fusion
make check
```

## Documentation

L'index complet est dans [`docs/README.md`](docs/README.md).

## Licence et sécurité

Voir [`LICENSE`](LICENSE) et [`SECURITY.md`](SECURITY.md).
