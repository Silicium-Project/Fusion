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
| Découpage d'un job en fragments | oui | non |
| Attribution d'une tâche à un seul nœud (claim, bail, retry) | oui | non : chaque nœud qui reçoit le gossip calcule |
| Transfert des entrées / résultats entre pairs | blobs par `content_id` | non : chemins de fichiers locaux |
| Vérification par un autre pair | oui | non : auto-vérification |
| Réassemblage, reçus, facturation | oui | non |
| NAT : connexion directe + relais | ICE, punch UDP, relais HTTP, TURN | AutoNAT + relais serveur seulement |
| API de contrôle pour le BackEnd | `/gossip/publish` + fichiers | `/publish`, `/tasks/{id}` (sans authentification) |

## Bloquants de sécurité (à corriger avant toute installation chez un utilisateur)

1. Une tâche reçue par gossip peut fixer `runtime_image`, `runtime_workdir` et
   `runtime_env` (`crates/node-core/src/p2p.rs`, `runtime.rs`) : n'importe quel
   pair peut lancer une image Docker arbitraire avec un dossier de l'hôte monté.
2. `scene_path` et `output_path` voyagent tels quels entre machines : un pair
   distant choisit quel fichier est lu et lequel est écrasé.
3. Les routes HTTP du nœud (`/publish`, `/tasks/{id}`) n'ont pas d'authentification
   (elles écoutent sur `127.0.0.1`, mais rien n'empêche de les exposer).
4. Tout pair abonné au topic peut publier une tâche qui sera exécutée.
5. La clé mesh `demo-mesh` est codée en dur dans l'app desktop publiée.

## Phases

| Phase | Contenu | Critère de sortie |
| --- | --- | --- |
| 0. Assainir | Dossiers par partie (`crates/`, `tools/dev/`, `docs/` rangé), vestiges supprimés, workspace Cargo et CI Rust unifiée | CI verte, aucun comportement changé |
| 1. Figer les contrats | Types Rust versionnés (tâche, fragment, reçu, événement) ; golden files capturés depuis le Python | Les types Rust relisent les sorties Python à l'identique |
| 2. Sécuriser le nœud Rust | Les 5 bloquants ci-dessus, timeouts, limites de ressources | Tests négatifs (tâche non signée, chemin `..`, API sans jeton) |
| 3. Pipeline raytracer en Rust | `crates/raytracer` devient une bibliothèque : découpage, jalons, vérification, réassemblage | Rendu octet pour octet identique au corpus golden |
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
