# Guide du dépôt Network (pour les contributeurs et les agents)

Network est le dépôt du runtime réseau de Silicium, intégré dans Fusion comme
sous-module. Carte détaillée : `docs/architecture/repository-layout.md`.

## Règle de langage

- **Rust** pour tout ce qui s'exécute chez un utilisateur ou sur le serveur →
  `crates/`.
- **Python** uniquement pour l'outillage développeur → `tools/dev/`, `tests/`.
- L'ancien runtime Python (nœud, CLI `silicium`, API MCP, `networked/`,
  `workloads/`) a été supprimé et ne doit pas revenir
  (`docs/architecture/rust-migration.md`).

## Où mettre quoi

| Besoin | Emplacement |
| --- | --- |
| Code du nœud, du calcul, de la réputation | `crates/<crate>/` |
| Programme on-chain, SDK | `solana-layer/` |
| Script de test, de démo, de contrôle qualité, de release | `tools/dev/<domaine>/` |
| Test Python (outillage) | `tests/` |
| Workload (découpage, calcul, vérification, assemblage) | `crates/p2p-node/src/workload/` (trait `Workload`) |
| Conteneur ou service local | `infra/` |
| Documentation | `docs/<architecture|contracts|operations|development>/` + `README.md` du dossier concerné |

Le déploiement de production (serveur, Compose du site, systemd) appartient à
Fusion (`deploy/`), pas à ce dépôt.

## Contrats à ne pas casser

- Fichiers lus par le BackEnd : `docs/contracts/backend-files.md`.
- API `/v1` du nœud, utilisée par le BackEnd (`crates/p2p-node/README.md`).
- Programme Solana, son IDL et ses tests (`solana-layer/`).

## Contrôles

```bash
make check                                             # contrôle rapide (CI)
cargo test --workspace --locked                        # tests Rust (workspace)
make e2e                                               # réseau local de bout en bout
python3 -m pytest -q                                   # tests de l'outillage Python
```

La CI de référence est `.github/workflows/ci.yml`.

## Hygiène

- Pas d'état généré dans Git (cibles Cargo, ledgers, caches, journaux, wallets,
  secrets).
- Fichiers courts et lisibles : au-delà de ~400 lignes, découper en modules.
- Chaque dossier a un `README.md` à jour ; chaque module a un en-tête qui dit
  ce qu'il fait.
- Les composants supprimés (chaîne C++, viewer Qt, démos d'assembleur, corpus PE,
  fallback Python du raytracer, runtime Python) ne doivent pas revenir.
