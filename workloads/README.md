# workloads/ — orchestration des workloads (Python, legacy)

> **Legacy.** Le **rendu** est déjà en Rust (`crates/raytracer`). Ce qui reste en
> Python ici — découpage, vérification, réassemblage, orchestration d'un job —
> sera porté dans `crates/raytracer` et l'ordonnanceur Rust
> (voir `docs/architecture/rust-migration.md`).

| Chemin | Rôle | Utilisé par |
| --- | --- | --- |
| `raytracer/raytracer_workload.py` | Sous-commandes `split`, `compute`, `verify`, `reassemble`, `validate` ; appelle le binaire natif | `tools/network_node.py` |
| `raytracer/run_network_job.py` | Orchestration complète d'un job de rendu (fragments, défis de vérification, reçus, progression) | BackEnd Go (`internal/silicium/runner.go`) |
| `raytracer/split.py`, `compute.py`, `verify.py`, `reassemble.py` | Points d'entrée minces vers `raytracer_workload.py` | `tools/network_node.py` (sous-processus) |
| `raytracer/examples/` | Scènes `.cfg` d'exemple | tests, démos |
| `raytracer/workload.json` | Manifeste du workload | catalogue, CLI |
| `standard/` | Workloads « standard » (SHA-256, multiplication de matrices, Monte-Carlo…) | `tools/network_node.py` |
| `common.py` | Utilitaires partagés : hash, soumission de tâches à un export, références P2P, wallet Solana, PPM → PNG | workloads |

Les manifestes et golden data de tous les workloads sont dans
[`../catalog/workloads/`](../catalog/workloads/).
