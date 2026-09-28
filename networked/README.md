# networked/ — paquet Python `networked` (legacy)

> **Legacy.** Ce dossier fait partie du runtime Python de production qui sera
> remplacé par `crates/` (voir `docs/architecture/rust-migration.md`). Ne pas y
> ajouter de fonctionnalités ; les correctifs restent possibles.

| Fichier | Rôle | Utilisé par |
| --- | --- | --- |
| `networked_runtime.py` | Gestion des blobs de contenu attachés aux tâches (`attach_network_content_blobs`) et lancement d'un nœud de ressources local | `tools/network_node.py`, `workloads/raytracer/run_network_job.py`, app desktop (copié dans le runtime installé) |
| `start-node.cmd` | Lanceur Windows de développement d'un nœud Python | `Fusion/start-silicium-local.ps1` |

Le code Rust qui se trouvait ici a été déplacé dans [`../crates/`](../crates/).
