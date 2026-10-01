# Organisation du dépôt Network

```text
Network/
├── Cargo.toml, Cargo.lock     # workspace Cargo unique (toutes les crates de crates/)
├── crates/                    # Rust — runtime cible (s'exécute chez l'utilisateur / sur le serveur)
│   ├── node-core/             #   types, journal de tâches signé, réputation, matériel, runtime WASM/OCI
│   ├── p2p-node/              #   binaire du nœud : libp2p, API HTTP locale, traitement des tâches
│   ├── compute-daemon/        #   service local de calcul et de vérification (lance le raytracer)
│   ├── reputation-bridge/     #   scores de réputation et vérification de stake Solana
│   └── raytracer/             #   moteur de rendu natif déterministe (binaire silicium-raytracer)
├── solana-layer/              # Anchor (Rust) + SDK TypeScript + tests — workspace séparé
│
├── tools/                     # Python LEGACY — runtime de production encore actif
│   ├── network_node.py        #   le nœud Python (orchestrateur VPS + nœuds utilisateurs)
│   ├── mcp_server.py          #   API expérimentale MCP (service systemd sur le VPS)
│   ├── mcp/                   #   implémentation du serveur MCP (un module par responsabilité)
│   ├── direct_transport.py    #   NAT traversal (ICE)
│   ├── rpc_*.py               #   RPC ZeroMQ
│   ├── runtime_telemetry.py, resource_intelligence.py, receipt_verification.py, i18n.py
│   ├── solana_layer_bridge.cjs#   pont Node.js vers le programme Solana
│   ├── cli/                   #   implémentation de la CLI `silicium` (livrée avec l'app)
│   └── dev/                   # Python OUTILLAGE — ne part jamais en production
│       ├── e2e/               #     scénarios Docker E2E, workers de test, test de charge
│       ├── world/             #     démo « world mesh » et son interface
│       ├── quality/           #     contrôles UTF-8, i18n, budgets de performance
│       ├── release/           #     manifeste de mise à jour, preflight Solana devnet
│       └── tui/               #     interface terminal opérateur
├── networked/                 # Python LEGACY — paquet networked (blobs de contenu)
├── workloads/                 # workloads : manifestes, registre, handlers (Python legacy), fixtures, golden
│
├── tests/                     # tests pytest (+ fixtures/)
├── proto/                     # contrat RPC protobuf (legacy)
├── i18n/                      # traductions CLI et shell
├── infra/                     # Docker (Solana local, bootstrap, world), systemd
├── ci/                        # scripts de CI
├── docs/                      # documentation, rangée par partie
├── silicium                   # CLI développeur et lanceur de nœud (point d'entrée de tools/cli/)
└── Makefile                   # raccourcis : check, test, rust-test, rust-lint, raytracer-test
```

## Règles

- **Du nouveau code runtime va dans `crates/`.** Rien de nouveau dans `tools/`,
  `networked/` ou `workloads/` hors correctifs : ces dossiers disparaissent à la
  fin de la migration ([`rust-migration.md`](rust-migration.md)).
- **Tout script Python qui ne sert qu'aux développeurs va dans `tools/dev/<domaine>/`.**
- **Pas d'état généré dans Git** : cibles Cargo, ledgers, caches, journaux,
  wallets et secrets sont ignorés par `.gitignore`.
- Les composants supprimés (chaîne C++ `splitter`/`executor`/`worker`, viewer Qt,
  démos d'assembleur, corpus PE, fallback Python du raytracer) ne doivent pas
  revenir. Leur historique reste dans Git.
