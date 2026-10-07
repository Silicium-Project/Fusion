# Contrat implicite : fichiers lus par le BackEnd

Le BackEnd Go lit directement sur le disque des fichiers JSON et PNG produits par
le runtime Python. Ce contrat n'est défini nulle part ailleurs : **tout
remplaçant du runtime (nœud Rust) doit soit écrire ces fichiers à l'identique,
soit les exposer par l'API `/v1` et faire évoluer le BackEnd en même temps.**
Sans eux, la progression, les aperçus, la facturation et la télémétrie des pairs
disparaissent du FrontEnd sans erreur.

| Fichier | Producteur actuel | Lecteur (BackEnd) | Champs utilisés |
| --- | --- | --- | --- |
| `<workload_storage>/raytracer/<job>/raytracer-progress.json` | `workloads/raytracer/run_network_job.py` | `internal/handler/jobController.go` | progression ; `fragments[].receipt_attestation.accepted`, `compute_billable_work_units`, `verify_billable_work_units`, `compute_receipt_hash`, `verify_receipt_hash` |
| résumé du job (`SummaryPath`) | `run_network_job.py` | `internal/silicium/runner.go` (`parseRaytracerSummary`) | `success`, `failure_detail` / `error`, `reassembled_png` / `result_png_path` / `result_path` / `reassembled_ppm`, `devnet_trace.*`, `billing.billable_work_units`, `billing.receipt_set_hash` |
| `<dossier du job>/fragments/fragment-NNN.png` | `run_network_job.py` | `GetJobFragmentPreview` | aperçu d'un fragment |
| `<workload_storage>/embedding/<job>/raytracer-progress.json` et `raytracer-summary.json` | nœud Rust (`compatibility.rs`), recherche dans des documents | `jobArtifacts.go`, `runner.go` | comme ci-dessus, plus `fragments[].items` (passages du fragment, pour la progression) et `index_path` / `result_path` |
| `<workload_storage>/embedding/<job>/index/{index.json,vectors.f32,passages.jsonl}` | nœud Rust | `documentJobs.go` (export ZIP, résumé `documents` / `skipped` / `passage_count` de `index.json`) | format `silicium-index/1` (`docs/architecture/embedding-workload.md`) |
| `<export orchestrateur>/node.<id>.peers.json` | `tools/network_node.py` | `networkController.go` | liste des pairs connus |
| `<export orchestrateur>/node.<id>.heartbeat.json` | `tools/network_node.py` | `networkTelemetry.go` | `roles`, `app_version`, `release_channel`, `release_build`, `capacity`, `activity`, `task_queue`, `telemetry` |
| `<export orchestrateur>/node.<id>.metrics.json` | `tools/network_node.py` | `networkTelemetry.go` | horodatage et métriques du pair |

Chemins configurés côté BackEnd par `SILICIUM_WORKLOAD_STORAGE_DIR`,
`SILICIUM_ORCHESTRATOR_EXPORT_DIR` et `SILICIUM_ORCHESTRATOR_NODE_ID`.

Les tests de compatibilité de la phase 1 de la migration doivent capturer un
exemplaire réel de chacun de ces fichiers comme *golden file*.
