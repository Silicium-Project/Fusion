# Organisation du dépôt Network

```text
Network/
├── Cargo.toml, Cargo.lock     # workspace Cargo unique (toutes les crates de crates/)
├── crates/                    # Rust — tout ce qui s'exécute chez l'utilisateur ou sur le serveur
│   ├── node-core/             #   types, journal de tâches signé, réputation, matériel, runtime WASM/OCI
│   ├── p2p-node/              #   binaire du nœud : libp2p, API HTTP locale, workloads (trait Workload)
│   ├── compute-daemon/        #   service local de calcul et de vérification (lance le raytracer)
│   ├── reputation-bridge/     #   scores de réputation et vérification de stake Solana
│   ├── raytracer/             #   moteur de rendu natif déterministe (binaire silicium-raytracer, scènes d'exemple)
│   └── embedding/             #   documents, passages, modèle épinglé, index de vecteurs
├── solana-layer/              # Anchor (Rust) + SDK TypeScript + tests — workspace séparé
│
├── tools/dev/                 # Python OUTILLAGE — ne part jamais en production
│   ├── quality/               #   contrôles UTF-8 et parité des traductions
│   └── release/               #   preflight Solana devnet
├── tests/                     # tests pytest de tools/dev/ et des fichiers d'infra
├── i18n/                      # traductions des scripts shell d'infra
├── infra/                     # Docker (validateur Solana local, proxy, nœud d'amorçage)
├── ci/                        # scripts de CI (core_check.sh, e2e.sh, runner/)
├── docs/                      # documentation, rangée par partie
└── Makefile                   # raccourcis : check, test, e2e, rust-test, rust-lint, tools-test
```

## Règles

- **Le code runtime va dans `crates/`**, en Rust. Un nouveau calcul est un
  nouveau `Workload` dans `crates/p2p-node/src/workload/`.
- **Python seulement pour l'outillage développeur** : `tools/dev/<domaine>/`,
  testé dans `tests/`.
- **Pas d'état généré dans Git** : cibles Cargo, ledgers, caches, journaux,
  wallets et secrets sont ignorés par `.gitignore`.
- Les composants supprimés (runtime Python : `tools/network_node.py`,
  `tools/node/`, `tools/mcp_server.py`, RPC ZeroMQ, `networked/`, catalogue
  `workloads/`, CLI `silicium`, TUI ; chaîne C++, viewer Qt, démos
  d'assembleur, corpus PE) ne doivent pas revenir. Leur historique reste dans Git.
