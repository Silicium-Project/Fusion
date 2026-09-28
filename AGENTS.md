# Guide du dépôt Network (pour les contributeurs et les agents)

Network est le dépôt du runtime réseau de Silicium, intégré dans Fusion comme
sous-module. Carte détaillée : `docs/architecture/repository-layout.md`.

## Règle de langage

- **Rust** pour tout ce qui s'exécute chez un utilisateur ou sur le serveur →
  `crates/`.
- **Python** uniquement pour l'outillage développeur → `tools/dev/`, `tests/`.
- Le runtime Python encore en production (`tools/*.py`, `networked/`,
  `workloads/`) est **legacy** : correctifs oui, nouvelles fonctionnalités non.
  Plan : `docs/architecture/rust-migration.md`.

## Où mettre quoi

| Besoin | Emplacement |
| --- | --- |
| Code du nœud, du calcul, de la réputation | `crates/<crate>/` |
| Programme on-chain, SDK | `solana-layer/` |
| Script de test, de démo, de contrôle qualité, de release | `tools/dev/<domaine>/` |
| Test Python | `tests/` (fixtures dans `tests/fixtures/`) |
| Manifeste ou golden data de workload | `catalog/workloads/` |
| Conteneur ou service local | `infra/` |
| Documentation | `docs/<architecture|contracts|operations|development>/` + `README.md` du dossier concerné |

Le déploiement de production (serveur, Compose du site, systemd) appartient à
Fusion (`deploy/`), pas à ce dépôt.

## Contrats à ne pas casser

- Fichiers lus par le BackEnd : `docs/contracts/backend-files.md`.
- Chemin `workloads/raytracer/run_network_job.py`, appelé par le BackEnd.
- Programme Solana, son IDL et ses tests (`solana-layer/`).

## Contrôles

```bash
make check                                             # contrôle rapide (CI)
python3 -m pytest                                      # tests Python
cargo test --workspace --locked                        # tests Rust (workspace)
```

La CI de référence est `.github/workflows/ci.yml`.

## Hygiène

- Pas d'état généré dans Git (cibles Cargo, ledgers, caches, journaux, wallets,
  secrets).
- Fichiers courts et lisibles : au-delà de ~400 lignes, découper en modules.
- Chaque dossier a un `README.md` à jour ; chaque module a un en-tête qui dit
  ce qu'il fait.
- Les composants supprimés (chaîne C++, viewer Qt, démos d'assembleur, corpus PE,
  fallback Python du raytracer) ne doivent pas revenir.
