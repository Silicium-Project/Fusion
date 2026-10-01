# tools/ — runtime Python (legacy) et outillage

Ce dossier contient deux choses bien séparées :

1. **À la racine de `tools/` : le runtime Python encore utilisé en production.**
   Il sera remplacé par `crates/` (voir
   [`docs/architecture/rust-migration.md`](../docs/architecture/rust-migration.md)).
   Pas de nouvelle fonctionnalité ici.
2. **Dans [`dev/`](dev/) : l'outillage des développeurs**, qui reste en Python et
   n'est jamais lancé en production.

## Runtime de production (legacy)

| Fichier | Rôle | Lancé / importé par |
| --- | --- | --- |
| `network_node.py` | Point d'entrée et façade de compatibilité du nœud Python (orchestrateur sur le VPS, nœud de calcul chez l'utilisateur) | `silicium node start`, `Fusion/deploy/linux/start-orchestrator.sh`, app desktop |
| [`node/`](node/) | Implémentation du nœud, découpée par fonctionnalité (`peer/`, `daemon/`, `cli.py`…) | `network_node.py` |
| `mcp_server.py` | Point d'entrée (compatibilité) de l'API expérimentale MCP authentifiée ; ré-exporte `tools/mcp_ingress/` | service systemd `silicium-experiment-api` (Fusion), `silicium mcp serve`, tests |
| [`mcp_ingress/`](mcp_ingress/) | Implémentation du serveur MCP/HTTP : files de tâches et de requêtes, routes HTTP, transport MCP, authentification, snapshots, métriques | `mcp_server.py`, `workloads/common.py`, `tools/cli/node/api.py`, `rpc_server.py` (via `mcp_server`) |
| `direct_transport.py` | Traversée de NAT et transfert direct entre pairs (ICE via `aioice`) | `node/` |
| `rpc_server.py`, `rpc_client.py`, `rpc_protocol.py` | RPC ZeroMQ (contrat : `proto/silicium_rpc.proto`) | `mcp_server.py`, `run_network_job.py` |
| `runtime_telemetry.py` | Échantillonnage CPU / mémoire du nœud | `node/` |
| `resource_intelligence.py` | Profil de ressources et réputation par ressource | `node/` |
| `receipt_verification.py` | Vérification des reçus de calcul | `workloads/raytracer/run_network_job.py` |
| `solana_layer_bridge.cjs`, `node_uuid_cjs_shim.cjs` | Pont Node.js vers le programme Solana | `node/solana_bridge.py`, CLI `silicium` |
| `i18n.py` | Traductions de la CLI et des outils | CLI, TUI, contrôles i18n |
| `node_defaults.py` | Valeurs par défaut communes au nœud et à la CLI (mode world, synchro des pairs, STUN) | `node/`, `silicium node start` |
| [`cli/`](cli/) | Implémentation de la CLI `silicium` (livrée avec l'app desktop) | `Network/silicium`, `python -m tools.cli` |

## Outillage développeur

Voir [`dev/README.md`](dev/README.md).
