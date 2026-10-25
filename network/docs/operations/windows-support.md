# Support de Windows

Ce que l'on peut faire sur Windows avec le dépôt Network.

## Chez l'utilisateur

L'application de bureau (Fusion `apps/silicium-node`) embarque les binaires
Rust `p2p_node.exe`, `compute_daemon.exe` et `silicium-raytracer.exe`. Aucun
Python ni Docker n'est nécessaire.

## Pour un développeur

| Tâche | Windows natif (PowerShell) | WSL2 |
| --- | --- | --- |
| `cargo build`, `cargo test --workspace` | oui | oui |
| Tests de l'outillage (`python -m pytest -q`, Python 3.11+, `requirements-dev.txt`) | oui | oui |
| Scripts bash (`ci/*.sh`, `crates/p2p-node/scripts/e2e-local.sh`, `infra/**/*.sh`) | non | oui |
| Validateur Solana local et proxy (`infra/docker-compose.yml`) | Docker Desktop | Docker Desktop (intégration WSL) |

Conseil : rester dans un seul environnement (tout Windows ou tout WSL) pour
éviter les soucis de chemins et de fins de ligne.
