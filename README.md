# Silicium Network

`Network` contient le runtime distribué de Silicium. Le chemin de production
est le nœud Rust `silicium-node`, accompagné de `compute_daemon` pour
l'exécution et de `reputation_bridge` pour la réputation. Les anciens
pipelines C++ (`splitter`, `executor`, `worker`, viewer Qt et démos associées)
ne font pas partie du produit ; ils ne subsistent que dans l'historique Git.

## Composants actifs

- `networked/p2p_node/` : binaire Rust `silicium-node`, découverte des pairs,
  persistance locale, gossip et API de contrôle versionnée.
- `networked/compute_daemon/` : exécuteur Rust des workloads de calcul.
- `networked/reputation_bridge/` : service de réputation consommé par le
  nœud et la stack Fusion.
- `networked/silicium_node_core/` : primitives de transport, planification et
  registre des tâches du nœud.
- `workloads/raytracer/` et `catalog/` : workload de référence et manifests.
- `solana-layer/` : programme Anchor, SDK TypeScript, IDL et tests Solana.
- `tools/` : outils de développement, migration et contrôle ; ils ne sont pas
  le runtime de nœud par défaut.

## Contrat de contrôle

Fusion communique directement avec l'API HTTP du nœud Rust :

- `GET /v1/health`
- `GET` et `POST /v1/tasks`
- `POST /v1/workloads/{root_job_id}/cancel`
- `GET /v1/peers`

Les routes, l'authentification Bearer et la compatibilité sont décrites dans
[docs/node-control-api.md](docs/node-control-api.md). Les routes non versionnées
restantes sont de compatibilité interne et ne doivent pas servir à de nouveaux
consommateurs.

## Développement local

Lancer les deux services Rust dans deux terminaux :

```bash
SILICIUM_COMPUTE_BIND=127.0.0.1:9090 \
  cargo run --manifest-path networked/compute_daemon/Cargo.toml

SILICIUM_NODE_ID=local-node \
SILICIUM_NODE_ROLES=compute,verify \
SILICIUM_NODE_CONTROL_TOKEN=local-dev-token \
SILICIUM_API_BIND=127.0.0.1 \
API_PORT=9092 \
COMPUTE_DAEMON_URL=http://127.0.0.1:9090 \
  cargo run --manifest-path networked/p2p_node/Cargo.toml
```

La stack complète du site (FrontEnd, BackEnd, nœud, compute et proxy) est
définie au niveau de Fusion, dans `deploy/compose/docker-compose.yml`.

## Vérifications

```bash
python -m pytest
cargo test --manifest-path networked/p2p_node/Cargo.toml --locked
cargo test --manifest-path networked/compute_daemon/Cargo.toml --locked
cd solana-layer/silicium-sdk && npm ci && npm run build && npm run verify:dist
```

La CI exécute aussi les tests du bridge de réputation et vérifie que le `dist`
du SDK est régénéré. La gate Compose de Fusion ouvre réellement le FrontEnd
dans un navigateur et contrôle le chemin FrontEnd → BackEnd → nœud Rust.

## Documentation utile

- [Contrat HTTP du nœud](docs/node-control-api.md)
- [Transport P2P direct](docs/p2p-direct-transport-contract.md)
- [Organisation du dépôt](docs/repository-layout.md)
- [Workloads et fixtures](docs/workload-fixtures.md)
- [Intégration Solana Devnet](docs/solana-devnet.md)

## État généré

Les caches, ledgers, sorties Cargo, `node_modules`, clés et journaux sont
ignorés par Git. Ne les ajoutez pas au dépôt et utilisez les scripts CI qui
nettoient leur propre espace de travail entre les builds.
