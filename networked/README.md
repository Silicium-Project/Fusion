# Runtime réseau Rust

Ce répertoire contient les services déployés du runtime Silicium :

- `p2p_node/` produit le binaire `silicium-node` ;
- `compute_daemon/` exécute et vérifie les workloads ;
- `reputation_bridge/` expose la réputation au nœud ;
- `silicium_node_core/` contient les primitives partagées.

`silicium-node` est le point d'entrée officiel. Il expose une API de contrôle
HTTP versionnée sur le port `9092` par défaut et utilise `compute_daemon` sur
le port `9090`. La configuration de production se fait dans Fusion ; voir
[`../docs/node-control-api.md`](../docs/node-control-api.md) et
`Fusion/deploy/compose/docker-compose.yml`.

Pour les tests locaux, lancer `compute_daemon` avant le nœud :

```bash
SILICIUM_COMPUTE_BIND=127.0.0.1:9090 \
  cargo run --manifest-path compute_daemon/Cargo.toml

SILICIUM_NODE_ID=local-node \
SILICIUM_NODE_CONTROL_TOKEN=local-dev-token \
COMPUTE_DAEMON_URL=http://127.0.0.1:9090 \
  cargo run --manifest-path p2p_node/Cargo.toml
```

Les anciens scripts de démo Python ne constituent plus une procédure de
démarrage ou de déploiement supportée.
