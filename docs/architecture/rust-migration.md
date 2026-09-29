# Migration du runtime vers Rust

**Règle du projet :** Rust pour tout ce qui s'exécute chez un utilisateur ou sur
le serveur ; Python uniquement pour l'outillage des développeurs (tests, E2E,
démos, contrôles qualité, scripts de release).

Le BackEnd Go, le FrontEnd Nuxt et le SDK TypeScript Solana restent dans leur
langage : la migration concerne le runtime réseau.

## Pourquoi on ne peut pas migrer nœud par nœud

Les nœuds Python parlent HTTP + gossip maison avec une clé mesh partagée ; les
nœuds Rust parlent libp2p. Il n'y a aucun protocole commun. La bascule se fait
donc **pour tout le réseau à la fois** (canal `dev`, puis `prod` avec mise à jour
forcée de l'app), une fois que le nœud Rust a rattrapé le Python.

## Ce qui manque au nœud Rust

| Capacité | Python (prod) | Rust (`crates/p2p-node`) |
| --- | --- | --- |
| Découpage d'un job en fragments | oui | logique portée (`silicium_raytracer::pipeline::tiles`), pas encore branchée dans le nœud |
| Attribution d'une tâche à un seul nœud (claim, bail, retry) | oui | non : chaque nœud qui reçoit le gossip calcule |
| Transfert des entrées / résultats entre pairs | blobs par `content_id` | non : chemins de fichiers locaux |
| Vérification par un autre pair | oui | non : vérification locale contre l'engagement de jalons (logique portée : `pipeline::milestones`, `pipeline::sampling`) |
| Réassemblage, reçus, facturation | oui | réassemblage et PNG portés (`pipeline::reassemble`, `pipeline::png`) ; reçus et facturation non |
| NAT : connexion directe + relais | ICE, punch UDP, relais HTTP, TURN | AutoNAT + relais serveur seulement |
| API de contrôle pour le BackEnd | `/gossip/publish` + fichiers | `/publish`, `/tasks/{id}` (sans authentification) |

## Bloquants de sécurité

| # | Problème | État |
| --- | --- | --- |
| 1 | Une tâche reçue par gossip pouvait fixer `runtime_image`, `runtime_workdir` et `runtime_env` (image Docker arbitraire, dossier de l'hôte monté) | **Corrigé** : `TaskEnvelope::sanitize_remote` refuse les images OCI et retire dossier et environnement ; WASM seulement si `SILICIUM_ALLOW_REMOTE_WASM=1` |
| 2 | `scene_path` / `output_path` choisis par un pair distant | **Corrigé** : chemins relatifs sans `..` résolus dans le dossier de travail (`node-core::sandbox`) ; sortie choisie localement ; le compute-daemon refuse tout chemin hors de `SILICIUM_COMPUTE_ROOT` |
| 3 | API du nœud sans authentification | **Corrigé** : `SILICIUM_NODE_CONTROL_TOKEN` (bearer) ; écoute hors loopback refusée sans jeton ; idem pour le compute-daemon (`SILICIUM_COMPUTE_TOKEN`) |
| 4 | Tout pair du topic peut faire exécuter une tâche | **Corrigé** : seules les tâches signées par un éditeur de confiance (`SILICIUM_TRUSTED_PUBLISHERS`) sont exécutées |
| 5 | Clé mesh `demo-mesh` codée en dur dans l'app desktop publiée | **Ouvert** : concerne le réseau Python ; à remplacer par une clé fournie par le pipeline de release (secret) en même temps sur le VPS et dans l'app |

## Phases

| Phase | Contenu | Critère de sortie |
| --- | --- | --- |
| 0. Assainir | Dossiers par partie (`crates/`, `tools/dev/`, `docs/` rangé), vestiges supprimés, workspace Cargo et CI Rust unifiée | CI verte, aucun comportement changé |
| 1. Figer les contrats | Types Rust versionnés (tâche, fragment, reçu, événement) ; golden files capturés depuis le Python | Les types Rust relisent les sorties Python à l'identique |
| 2. Sécuriser le nœud Rust | Les 5 bloquants ci-dessus, timeouts, limites de ressources | Tests négatifs (tâche non signée, chemin `..`, API sans jeton) — **fait pour 1 à 4** ; reste la clé mesh (5) et les limites de ressources |
| 3. Pipeline raytracer en Rust | `crates/raytracer` devient une bibliothèque : découpage, jalons, vérification, réassemblage | Rendu octet pour octet identique au corpus golden — **fait** (tests de parité `crates/raytracer/tests/python_parity.rs`) |
| 4. Ordonnanceur et transport | Claim/bail/retry/annulation, blobs libp2p, relais client + DCUtR, vérification croisée, reprise après redémarrage | Test d'intégration à 3 nœuds |
| 5. Parité BackEnd / FrontEnd / Solana | API `/v1` complète (progression, fragments, reçus), télémétrie, séquence Solana identique | Tests Go + Playwright, `devnet_minimal_job_flow.ts` |
| 6. Bascule | Orchestrateur Rust sur le VPS, app lançant directement le binaire, plus de clé mesh | Canal `dev` stable une semaine, installeur sans Python |
| 7. Nettoyage | Suppression de `tools/*.py` runtime, `networked/`, `workloads/*.py`, dépendance `python3` des paquets | Contrôle CI : aucun service de prod ne lance Python |

## Correspondance Python → Rust

| Python (legacy) | Remplacé par |
| --- | --- |
| `tools/network_node.py` | `crates/p2p-node` + ordonnanceur + API `/v1` |
| `tools/direct_transport.py` | libp2p (Circuit Relay v2 + DCUtR) — pas de portage ligne à ligne |
| `tools/runtime_telemetry.py` | crate `telemetry` (`tracing` + métriques) |
| `tools/resource_intelligence.py` | `crates/node-core` (`hardware.rs`, `beta.rs`) |
| `tools/rpc_*.py`, `proto/` | disparaissent (plus de ZeroMQ) |
| `tools/solana_layer_bridge.cjs` | `crates/reputation-bridge` ou petit service TypeScript isolé |
| `networked/networked_runtime.py` | `crates/node-core` (blobs de contenu) |
| `workloads/raytracer/*.py` | `crates/raytracer` (bibliothèque) |
| `workloads/standard/*.py` | trait `Workload`, si ces workloads sont conservés |
| `tools/mcp_server.py` | décision ouverte : porter ou supprimer |

## Décisions ouvertes

- Sort de l'API expérimentale MCP (`tools/mcp_server.py`).
- Conservation des workloads « standard » dans la v1 Rust.
- Solana côté nœud : Rust natif ou service TypeScript isolé.
- Contrat de progression : fichiers JSON écrits par le Rust, ou `GET /v1/workloads/{id}`.
