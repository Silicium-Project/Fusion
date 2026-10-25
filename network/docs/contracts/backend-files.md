# Contrat : fichiers lus par le BackEnd

Le BackEnd Go lit directement sur le disque des fichiers JSON et PNG écrits par
l'orchestrateur (`p2p_node`, module `crates/p2p-node/src/compatibility.rs`).
Ce format vient de l'ancien runtime Python et a été conservé à l'identique :
**toute évolution de ces fichiers doit se faire en même temps dans le nœud et
dans le BackEnd** (ou passer par l'API `/v1`). Sans eux, la progression, les
aperçus, la facturation et la télémétrie des pairs disparaissent du FrontEnd
sans erreur.

| Fichier | Producteur | Lecteur (BackEnd) | Champs utilisés |
| --- | --- | --- | --- |
| `<workload_storage>/raytracer/<job>/raytracer-progress.json` | `compatibility.rs` (`write_job_files`) | `internal/handler/jobController.go` | progression ; `fragments[].receipt_attestation.accepted`, `compute_billable_work_units`, `verify_billable_work_units`, `compute_receipt_hash`, `verify_receipt_hash` |
| résumé du job (`SummaryPath`) | `compatibility.rs` (`write_job_files`) | `internal/silicium/runner.go` (`parseRaytracerSummary`) | `success`, `failure_detail` / `error`, `reassembled_png` / `result_png_path` / `result_path` / `reassembled_ppm`, `billing.billable_work_units`, `billing.receipt_set_hash` ; pour la trace blockchain (`internal/chainproof`) : `job_id`, `workload`, `fragments[].task_id` / `fragment_index` / `status` / `result_hash` / `worker` et `fragments[].trace` (voir ci-dessous) |
| `<dossier du job>/fragments/fragment-NNN.png` | `compatibility.rs` (`write_fragment_preview`) | `GetJobFragmentPreview` | aperçu d'un fragment |
| `<workload_storage>/embedding/<job>/raytracer-progress.json` et `raytracer-summary.json` | `compatibility.rs`, recherche dans des documents | `jobArtifacts.go`, `runner.go` | comme ci-dessus, plus `fragments[].items` (passages du fragment, pour la progression) et `index_path` / `result_path` |
| `<workload_storage>/embedding/<job>/index/{index.json,vectors.f32,passages.jsonl}` | nœud Rust | `documentJobs.go` (export ZIP, résumé `documents` / `skipped` / `passage_count` de `index.json`) | format `silicium-index/1` (`docs/architecture/embedding-workload.md`) |
| `<workload_storage>/llm/<job>/raytracer-progress.json` et `raytracer-summary.json` | `compatibility.rs`, traitement par IA | `jobArtifacts.go`, `runner.go` | comme ci-dessus, plus `fragments[].items` et `answers_path` / `table_path` / `result_path` |
| `<workload_storage>/llm/<job>/fragments/fragment-NNN.jsonl` | `compatibility.rs` (`write_answers_preview`), une fois la partie vérifiée | `batchAIJobs.go` (`GET /jobs/{id}/answers` pendant le calcul) | `{"id","input","output"}` par ligne |
| `<workload_storage>/llm/<job>/answers/{answers.jsonl,answers.csv,result.json}` | nœud Rust | `batchAIJobs.go` (réponses, téléchargement CSV / JSON Lines), `jobDashboard.go` (`item_count`, `answered`, `model` de `result.json`) | format `silicium-llm-result/1` (`docs/architecture/llm-workload.md`) |
| `<workload_storage>/hf/<job>/raytracer-progress.json` et `raytracer-summary.json` | `compatibility.rs`, catalogue IA | `jobArtifacts.go`, `runner.go` | comme ci-dessus, plus `fragments[].items` et `answers_path` / `result_path` |
| `<workload_storage>/hf/<job>/answers/{answers.jsonl,result.json}` | nœud Rust | (étape suivante du BackEnd) | format `silicium-hf-result/1` (`docs/architecture/hf-workload.md`) |
| `<export orchestrateur>/node.<id>.peers.json` | `compatibility.rs` (`write_peer_files`) | `networkController.go` | liste des pairs connus |
| `<export orchestrateur>/node.<id>.heartbeat.json` | `compatibility.rs` (`write_peer_files`) | `networkTelemetry.go` | `roles`, `app_version`, `release_channel`, `release_build`, `capacity`, `activity`, `task_queue`, `telemetry` |
| `<export orchestrateur>/node.<id>.metrics.json` | `compatibility.rs` (`write_peer_files`) | `networkTelemetry.go` | horodatage et métriques du pair |

Chemins configurés côté BackEnd par `SILICIUM_WORKLOAD_STORAGE_DIR`,
`SILICIUM_ORCHESTRATOR_EXPORT_DIR` et `SILICIUM_ORCHESTRATOR_NODE_ID`.

## Trace signée d'une tâche (`fragments[].trace`)

Écrite par `crates/p2p-node/src/task_trace.rs` à partir du task book, absente
tant qu'aucun worker n'a été accepté. Les auteurs sont des identifiants du task
book (clé publique Ed25519 en hexadécimal), pas des peer id libp2p.

| Champ | Contenu |
| --- | --- |
| `publisher`, `proposal_event`, `spec_sha256` | orchestrateur, hash de l'événement `TaskProposed` signé, hash de la spécification |
| `attempt`, `worker`, `claim_event` | tentative tracée (la finalisée, sinon la dernière), worker accepté, hash de sa réclamation |
| `result_event`, `result_sha256` | hash de l'événement de résultat signé et du contenu du résultat |
| `verifiers[]` | `author`, `verdict` (`true` / `false` / `null`), `verification_event`, `self_verification` (worker seul qui vérifie son propre résultat) |
| `finalized` | l'orchestrateur a accepté ce résultat |

Le BackEnd ancre ces traces sur Solana (une transaction Memo par job, racine
de Merkle des tâches terminées) : voir `docs/operations/solana-devnet.md`.
