# Documentation technique — Network

| Dossier | Contenu |
| --- | --- |
| [`architecture/`](architecture/) | Vue d'ensemble, organisation du dépôt, migration Rust, politiques de conception |
| [`contracts/`](contracts/) | Contrats entre composants : fichiers lus par le BackEnd, transport P2P, MCP, logs, programme Solana, workloads |
| [`operations/`](operations/) | Exploitation : Solana devnet, testbed « world », support Windows |
| [`development/`](development/) | Travailler sur le dépôt : critères de stabilité, fixtures, golden corpus, tests de charge, budgets de perf, TUI, gestion du backlog |
| [`i18n/`](i18n/) | Contrat de traduction et contrôles |
| [`archive/`](archive/) | Documents datés conservés pour l'historique ; ne décrivent plus l'état actuel |

## Par où commencer

1. [`architecture/overview.md`](architecture/overview.md) — ce qui tourne aujourd'hui et la cible.
2. [`architecture/repository-layout.md`](architecture/repository-layout.md) — où se trouve chaque chose.
3. [`architecture/rust-migration.md`](architecture/rust-migration.md) — le plan pour remplacer le runtime Python.
4. [`contracts/backend-files.md`](contracts/backend-files.md) — le contrat qu'aucun remplaçant ne doit casser.

## Index

### Architecture
- [overview.md](architecture/overview.md)
- [repository-layout.md](architecture/repository-layout.md)
- [rust-migration.md](architecture/rust-migration.md)
- [interface-policy.md](architecture/interface-policy.md) — quand introduire une interface
- [resource-intelligence.md](architecture/resource-intelligence.md) — profil de ressources et réputation par ressource
- [embedding-workload.md](architecture/embedding-workload.md) — recherche dans des documents : formats, modèle épinglé, vérification, exploitation

### Contrats
- [backend-files.md](contracts/backend-files.md)
- [p2p-direct-transport-contract.md](contracts/p2p-direct-transport-contract.md)
- [mcp-connector-spec.md](contracts/mcp-connector-spec.md)
- [logging-schema.md](contracts/logging-schema.md)
- [job-registry-contract-spec.md](contracts/job-registry-contract-spec.md)
- [payment-contract-accounting-spec.md](contracts/payment-contract-accounting-spec.md)
- [workload-alignment-policy.md](contracts/workload-alignment-policy.md)

### Exploitation
- [solana-devnet.md](operations/solana-devnet.md)
- [world-mesh-docker.md](operations/world-mesh-docker.md)
- [windows-support.md](operations/windows-support.md)

### Développement
- [core-stability.md](development/core-stability.md)
- [golden-corpus.md](development/golden-corpus.md)
- [workload-fixtures.md](development/workload-fixtures.md)
- [load-testing.md](development/load-testing.md)
- [performance-budgets.md](development/performance-budgets.md)
- [tui.md](development/tui.md)
- [backlog-hygiene.md](development/backlog-hygiene.md)

La documentation du programme Solana est dans [`../solana-layer/docs/`](../solana-layer/docs/).
