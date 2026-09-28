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
| `network_node.py` | Le nœud Python : orchestrateur sur le VPS, nœud de calcul chez l'utilisateur | `silicium node start`, `Fusion/deploy/linux/start-orchestrator.sh`, app desktop |
| `mcp_server.py` | API expérimentale MCP authentifiée | service systemd `silicium-experiment-api` (Fusion) |
| `direct_transport.py` | Traversée de NAT et transfert direct entre pairs (ICE via `aioice`) | `network_node.py` |
| `rpc_server.py`, `rpc_client.py`, `rpc_protocol.py` | RPC ZeroMQ (contrat : `proto/silicium_rpc.proto`) | `mcp_server.py`, `run_network_job.py` |
| `runtime_telemetry.py` | Échantillonnage CPU / mémoire du nœud | `network_node.py` |
| `resource_intelligence.py` | Profil de ressources et réputation par ressource | `network_node.py` |
| `receipt_verification.py` | Vérification des reçus de calcul | `workloads/raytracer/run_network_job.py` |
| `solana_layer_bridge.cjs`, `node_uuid_cjs_shim.cjs` | Pont Node.js vers le programme Solana | `network_node.py`, CLI `silicium` |
| `i18n.py` | Traductions de la CLI et des outils | CLI, TUI, contrôles i18n |

## Outillage développeur

Voir [`dev/README.md`](dev/README.md).
