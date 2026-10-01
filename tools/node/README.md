# `tools/node/` — nœud réseau Silicium (runtime Python legacy)

Ce paquet contient le démon du nœud réseau (orchestrateur sur le VPS, nœuds de
calcul chez les particuliers), découpé par fonctionnalité. Il remplace l'ancien
fichier monolithique `tools/network_node.py`, qui reste le **point d'entrée** et
une **façade de compatibilité** (mêmes noms exportés, même CLI) :

```bash
python3 -m tools.network_node --help        # orchestrateur (Fusion : deploy/linux/start-orchestrator.sh)
python3 tools/network_node.py --help        # en script (test de charge, installeurs)
```

```python
from tools import network_node
network_node.main(argv)                     # tools/cli/node/start.py
```

Code legacy : correctifs oui, nouvelles fonctionnalités non (cible : `crates/`,
voir `docs/architecture/rust-migration.md`).

## Organisation

| Module | Rôle |
| --- | --- |
| `constants.py` | rôles, statuts terminaux, canaux de release, valeurs par défaut |
| `util.py` | temps, identifiants, JSON canonique, hachage, écritures atomiques |
| `config.py` | `NodeConfig`, instantané de capacité, contraintes de pairs |
| `identity.py` | `NodeIdentity` : clés Ed25519, signatures |
| `queue_state.py` | `QueueState` : curseurs de files, idempotence |
| `reputation.py` | `ReputationStore` : score local, mémoire bayésienne des ressources |
| `p2p_client.py` | `P2PClient` : récupération/stockage de contenu (fichier, pairs, HTTP, IPFS) |
| `role_runtime.py` | `RoleRuntime` : exécution des tâches et requêtes par rôle |
| `solana_bridge.py` | `SolanaBridge` : sous-processus Node.js vers le programme Solana |
| `envelopes.py` | mise en file des tâches/requêtes, blobs de contenu embarqués |
| `cli.py` | `parse_roles`, `build_arg_parser`, `main` |
| `peer/` | `PeerNetwork` : un mixin par fonctionnalité P2P (voir `peer/__init__.py`) |
| `peer/http/` | serveur HTTP des pairs : gestionnaire, tables de routes, routes par domaine |
| `daemon/` | `NetworkNode` : un mixin par fonctionnalité du démon (voir `daemon/__init__.py`) |

`PeerNetwork` (`peer/network.py`) et `NetworkNode` (`daemon/node.py`) sont
assemblés à partir de mixins qui partagent leur état via `self`. Les routes HTTP
sont résolues dans l'ordre des tables `GET_ROUTES` / `POST_ROUTES` de
`peer/http/handler.py` : cet ordre est significatif (préfixes).

## Correspondance avec le portage Rust

| Python (`tools/node/`) | Cible Rust |
| --- | --- |
| `identity.py`, `peer/security.py`, `peer/handshake.py` | identité et signatures de `crates/node-core` / `crates/p2p-node` |
| `peer/` (gossip, candidats, signaling, ICE, relais) | libp2p dans `crates/p2p-node` (pas de portage ligne à ligne) |
| `peer/http/` | API HTTP locale `/v1` de `crates/p2p-node` |
| `daemon/claims.py`, `daemon/pull_loop.py`, `daemon/queue.py`, `daemon/dispatch.py` | ordonnanceur (claim/bail/retry) |
| `daemon/task_control.py`, `daemon/reconcile.py` | annulation et reprise après redémarrage de l'ordonnanceur |
| `daemon/receipts.py`, `daemon/onchain*.py`, `solana_bridge.py` | `crates/reputation-bridge` |
| `reputation.py` | `crates/node-core` (`beta.rs`) |

## Règles

- Modules courts (< 400 lignes), un en-tête qui dit ce que fait le module.
- Imports absolus `tools.node...` ; aucun état global hors `util.ATOMIC_WRITE_LOCK`.
- Les fichiers écrits dans le répertoire d'export sont un contrat avec le
  BackEnd : `docs/contracts/backend-files.md`.
- Tests : `tests/test_network_node*.py`.
