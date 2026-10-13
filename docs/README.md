# Documentation technique — Network

| Dossier | Contenu |
| --- | --- |
| [`architecture/`](architecture/) | Vue d'ensemble, organisation du dépôt, migration Rust, politiques de conception |
| [`contracts/`](contracts/) | Contrats entre composants : fichiers lus par le BackEnd, programme Solana |
| [`operations/`](operations/) | Exploitation : Solana devnet, support Windows |
| [`development/`](development/) | Travailler sur le dépôt : gestion du backlog |
| [`i18n/`](i18n/) | Contrat de traduction et contrôles |
| [`archive/`](archive/) | Documents datés conservés pour l'historique ; ne décrivent plus l'état actuel |

## Par où commencer

1. [`architecture/overview.md`](architecture/overview.md) — ce qui tourne aujourd'hui et la cible.
2. [`architecture/repository-layout.md`](architecture/repository-layout.md) — où se trouve chaque chose.
3. [`architecture/rust-migration.md`](architecture/rust-migration.md) — comment le runtime Python a été remplacé par Rust (terminé).
4. [`contracts/backend-files.md`](contracts/backend-files.md) — le contrat qu'aucun remplaçant ne doit casser.

## Index

### Architecture
- [overview.md](architecture/overview.md)
- [repository-layout.md](architecture/repository-layout.md)
- [rust-migration.md](architecture/rust-migration.md)
- [interface-policy.md](architecture/interface-policy.md) — quand introduire une interface
- [embedding-workload.md](architecture/embedding-workload.md) — recherche dans des documents : formats, modèle épinglé, vérification, exploitation

### Contrats
- [backend-files.md](contracts/backend-files.md)
- [job-registry-contract-spec.md](contracts/job-registry-contract-spec.md)
- [payment-contract-accounting-spec.md](contracts/payment-contract-accounting-spec.md)

### Exploitation
- [solana-devnet.md](operations/solana-devnet.md)
- [windows-support.md](operations/windows-support.md)

### Développement
- [backlog-hygiene.md](development/backlog-hygiene.md)

La documentation du programme Solana est dans [`../solana-layer/docs/`](../solana-layer/docs/).
