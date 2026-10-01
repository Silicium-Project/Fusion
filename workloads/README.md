# workloads/ — tous les workloads du réseau

Un seul dossier pour tout ce qui concerne les workloads : leur **contrat**
(manifestes), la façon dont un nœud les **exécute** (handlers), et les données
de **contrôle** (fixtures, golden corpus). Il remplace l'ancien couple
`workloads/` (code) + `catalog/workloads/` (manifestes).

## Principe : un workload = un dossier

Le chemin du dossier **est** l'identifiant du workload :

```text
workloads/calcul/libm/sin/            → id calcul/libm/sin
├── manifest.yaml                     # contrat (schéma v2)
└── README.md                         # entrées / sorties, vérification, paiement
```

- `calcul/…` : tâches qui produisent un résultat (rôle réseau `compute`).
- `verification/…` : tâches qui vérifient un résultat (rôle réseau `verify`).

La section `runtime` du manifeste dit comment un nœud l'exécute :

```yaml
runtime:
  kind: python                                # exécutable par les nœuds
  handler: workloads.standard.handlers:libm   # module:fonction(WorkloadContext) -> dict
```

ou `kind: planned` pour un profil décrit mais qu'aucun nœud n'exécute encore
(Blender, FFmpeg, inférence ML…). `parameters` (facultatif) est transmis tel
quel au handler.

## Comment un nœud exécute une tâche

`tools/network_node.py` ne connaît aucun workload en particulier :

1. la tâche porte `workload: <id>` ;
2. `workloads.registry.run_workload(id, rôle, contexte)` cherche le manifeste
   (ou un alias) et appelle son handler avec un `WorkloadContext` (tâche, données
   d'entrée, `put_output`, `fetch`, `run_process`, `parameters`) ;
3. pas de handler : une tâche de calcul est renvoyée « non exécutée » avec la
   raison (`unsupported_workload`, `workload_not_executable`,
   `workload_role_mismatch`) ; une tâche de vérification sans vérificateur
   dédié passe par `verification/hash-audit/sha256` (comparaison de hash).

Les nœuds ne lisent pas le YAML (PyYAML n'est pas installé partout où un nœud
tourne) mais `index.json`, généré à partir des manifestes.

## Ajouter un workload

1. Créer `workloads/<calcul|verification>/<domaine>/<nom>/manifest.yaml` et son
   `README.md` (partir d'un manifeste existant).
2. S'il est exécutable : écrire le handler (`fonction(ctx: WorkloadContext) -> dict`)
   et le référencer dans `runtime.handler`.
3. `./silicium workload index` puis `./silicium workload lint`.

Aucun code du nœud n'est à modifier. Le lint vérifie le schéma, que l'`id`
correspond au dossier, que le handler s'importe, et que `index.json` est à jour.

## Contenu

| Chemin | Rôle |
| --- | --- |
| `calcul/`, `verification/` | Un dossier par workload (manifeste + README) |
| `schema/workload-manifest-v2.schema.json` | Schéma des manifestes |
| `index.json` | Index généré (`./silicium workload index`), lu par les nœuds |
| `registry.py` | Registre : chargement, alias, résolution du handler, `run_workload` |
| `standard/handlers.py` | Handlers des workloads intégrés (SHA-256, libm, matrices, Monte-Carlo π, audit de hash) |
| `standard/standard_workloads.py`, `standard/run.py` | Fonctions communes ; exécution locale d'un workload intégré (`python -m workloads.standard.run`) |
| `raytracer/node_tasks.py` | Handlers du raytracer : rendu d'une tuile, vérification d'un jalon |
| `raytracer/run_network_job.py` | Point d'entrée de l'orchestration d'un job de rendu complet (appelé par le BackEnd Go) |
| `raytracer/orchestrator/` | Implémentation de l'orchestrateur : découpage, dispatch, vérification, réassemblage (un module par étape) |
| `raytracer/raytracer_workload.py`, `compute.py`, `verify.py` | Rendu natif et vérification d'une tuile (le découpage et le réassemblage sont faits par le binaire `silicium-raytracer`) |
| `raytracer/examples/` | Scènes `.cfg` d'exemple |
| `fixtures/` | Fixtures versionnées (`fixtures.json`) et politique d'alignement |
| `golden/golden-corpus.json` | Corpus golden des plans d'exécution |
| `common.py` | Utilitaires partagés (hash, JSON stable, performances, PPM → PNG…) |

## Commandes

```bash
./silicium workload list [--category calcul --domain rendering --tag …]
./silicium workload show calcul/libm/sin [--dry-run --preset default]
./silicium workload index        # régénère index.json
./silicium workload lint         # schéma, id = dossier, handlers, index à jour
./silicium workload fixtures
./silicium workload alignment
./silicium workload golden --strict
```

Vocabulaire de `taxonomy` (catégories, domaines, complexité, profils de
ressources, déterminisme, tags) : voir le schéma v2.

## Hors de ce dossier

Le code Python d'exécution reste **legacy** : le rendu lui-même est déjà en Rust
(`crates/raytracer`) et le reste sera porté en Rust
(`docs/architecture/rust-migration.md`). Le nœud Rust expérimental
(`crates/p2p-node`) ne passe pas encore par ce registre : il n'exécute que le
raytracer, via `compute-daemon`.
