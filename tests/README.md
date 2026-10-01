# tests/ — tests pytest

Tests du runtime Python (legacy), de la CLI et des outils développeur.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest                    # tout
python3 -m pytest tests/test_network_node_*.py -q
```

| Fichiers | Couvre |
| --- | --- |
| `test_network_node_*.py` (+ `network_node_support.py`) | Le nœud Python (`tools/network_node.py`), un fichier par domaine : `identity` (identité, handshake, auth signée), `nat_traversal` (STUN, candidats, hole punching UDP), `signaling` (sessions de signalisation, attestations de chemin), `transport` (backends directs, ICE), `gossip_sync` (découverte, gossip, sync HTTP, relais, réplication), `updates` (annonces de mise à jour), `role_tasks` (exécution locale, vérification, reçus), `p2p_content` (récupération de contenu), `reputation_solana` (réputation, pont Solana), `dispatch` (dispatch distant, annulation), `claims` (claims des workers), `task_lifecycle` (vivacité, réconciliation). `network_node_support.py` contient les helpers partagés (`_config`, …). **C'est la meilleure spécification du comportement à reproduire en Rust.** |
| `test_raytracer_*.py`, `test_receipt_verification.py` | Pipeline raytracer Python, reçus |
| `test_mcp_server.py`, `test_rpc_protocol.py`, `test_silicium_*_cli.py` | API MCP, RPC, CLI |
| `test_e2e_*`, `test_load_test.py`, `test_world_*`, `test_tui_*`, `test_perf_budget.py`, `test_i18n_*`, `test_utf8.py`, `test_solana_integration_contract.py` | Outils de `tools/dev/` |
| `test_workload_*.py`, `test_manifests.py`, `test_standard_workloads.py` | Catalogue et workloads |
| `test_entrypoint.py` (+ `conftest.py`) | Script d'entrée du conteneur Solana (`infra/docker/solana-entrypoint.sh`) |
| `smoke/` | Smoke test du reverse proxy |
| `fixtures/python_raytracer.py` | Raytracer Python de référence **pour les tests uniquement** (pixels non identiques au binaire natif) |

Les tests Rust sont dans chaque crate ; on les lance depuis la racine du workspace (`cargo test --workspace`, ou `cargo test -p <paquet>`).
