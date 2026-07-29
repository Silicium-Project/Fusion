# Registre de triage des issues pour la refonte

Date : 29 juillet 2026  
Périmètre : Fusion, Network, BackEnd, FrontEnd

## 1. Principes de triage

Une issue ouverte doit représenter un résultat encore absent. Les issues purement historiques ou explicitement marquées `Done` doivent être fermées, puis référencées depuis les rapports/roadmaps si leur valeur documentaire reste utile.

Une issue n’est pas un second document d’architecture concurrent :

- Fusion porte composition, E2E, release et déploiement ;
- Network porte runtime, protocole, workloads et contrats réseau ;
- BackEnd porte API/persistence/orchestration web ;
- FrontEnd porte expérience Nuxt ;
- Network#247 est l’epic de migration native ;
- Network#257 est l’autorité normative sur le modèle sans scheduler central.

## 2. Fermetures immédiates recommandées

| Dépôt | Issue | Décision | Preuve |
|---|---:|---|---|
| Fusion | #67 | fermer `completed` | commit Network #237 + intégration Fusion #68 ; `LocalNetworkEmitter` présent |
| Network | #145 | fermer `completed` | snapshot store, rétention, export/import, tests et commit dédié présents |
| Network | #199 | fermer `completed` | titre/corps `Done`, scope et preuves déjà documentés |
| Network | #200 | fermer `completed` | titre/corps `Done`, réputation V2.5 et tests documentés |
| Network | #201 | fermer `completed` | titre/corps `Done`, SDK/smoke tests documentés |

Des commentaires de triage ont été ajoutés à ces cinq issues avant fermeture proposée.

## 3. Epics à conserver

| Issue | Rôle |
|---|---|
| Fusion#74 | umbrella produit et coordination cross-repo |
| Network#247 | retrait Python et runtime Rust/C++ modulaire |
| Network#257 | task book répliqué, décisions locales et indépendance VPS |
| Network#280 | workload Blender, après fondations protocole/runtime |
| Network#110 | i18n umbrella, tant que les enfants restent ouverts |
| Network#149 | Windows natif umbrella, tant que #150–#154 restent incomplets |

## 4. Issues à rescoping explicite

| Issue | Problème | Nouveau scope proposé |
|---|---|---|
| Network#122 | mot `scheduler` ambigu | politique locale de ressources/fairness/anti-starvation |
| Network#251 | peut réintroduire une orchestration centrale | workload host local + état dérivé du task book #257 |
| Fusion#84 | duplique la vérification milestones | tracker d’intégration/release seulement |
| Network#209 | recouvre Blender | fondation milestone générique et contrats |
| Network#284/#285 | dépendances implicites | spécialisation Blender de #209 |
| Network#75 | large et ancien | umbrella de remédiation viewer ownership |
| Network#174 | ciblé | patch GraphWindow, enfant effectif de #75/#102 |
| Network#205 | probablement partiellement livré | auditer le runtime actuel, fermer le livré, rouvrir seulement les gaps |
| Network#144 | concurrence partiellement présente | limiter au rate limiting, timeouts et backpressure manquants |
| Network#143 | bind local déjà par défaut | limiter à TLS + garde explicite de bind public |
| Network#15 | titre/scope faible | renommer ou convertir en tracker d’intégration Notebook concret |

## 5. Regroupements et dépendances

### Milestones et vérification

```text
Network#209 (contrat générique)
  -> Network#284 (Merkle/challenge Blender)
  -> Network#285 (quorum/probabilité/fraude Blender)
  -> Fusion#84 (intégration/E2E/release)
```

### Runtime natif

```text
Network#247
  -> fixtures de compatibilité
  -> #248 stockage/CAS
  -> #257 task book natif
  -> #250 gossip/peer directory
  -> #251 host/admission locale
  -> #252 ICE/relay
  -> #249 API/CLI
  -> #253 packaging/retrait Python
  -> #254 conformance/fuzz/perf/security
```

### P2P

```text
#257 task book
  -> #216 transferts directs
  -> #217 relay
  -> #218 desktop diagnostics
  -> #219 matrice de tests
  -> #220 operations/deployment
```

### Viewer

```text
#75 umbrella ownership
  -> #102 inventaire (closed)
  -> #174 GraphWindow
  -> autres patches issus de l’inventaire
```

## 6. Nouvelles issues de remédiation

Le plan idempotent `ISSUE_PLAN.json` crée les issues suivantes si un titre exact n’existe pas déjà.

### Fusion

1. `[Epic] Sanitize repositories and declare production/legacy lifecycle`
2. `[Security] Remove demo credentials and hard-coded production endpoints`
3. `[Build] Package only the declared production runtime`

### Network

4. `[Refactor] Freeze compatibility contracts and characterization tests before native migration`
5. `[CI] Make quality gates unconditional and add formatter/linter ratchets`
6. `[Repository hygiene] Remove generated artifacts and archive verified legacy components`

### BackEnd

7. `[Refactor] Extract typed network registry service and harden HTTP lifecycle`

### FrontEnd

8. `[Refactor] Split dashboard into typed components and composables`

Les corps complets, critères d’acceptation et contraintes sont versionnés dans `ISSUE_PLAN.json`.

## 7. Ordre de dépendance des nouvelles issues

```text
Lifecycle epic
  |-- Security config (parallèle, P0)
  |-- CI ratchets (parallèle, P1)
  |-- Compatibility fixtures
  |     `-- Network#247/#257 migration
  |-- Production runtime manifest
  |     `-- Network#253
  |-- BackEnd typed registry (après contrat API figé)
  |-- FrontEnd typed dashboard (après contrat API figé)
  `-- Repository hygiene/archive (après manifest + migration)
```

## 8. Politique de clôture

Fermer une issue comme `completed` lorsque :

- tous ses critères d’acceptation sont démontrés ;
- le code est sur la branche supportée ;
- les tests associés existent ou la preuve manuelle est explicitement acceptée ;
- les travaux futurs sont distincts et ont leur propre issue.

Fermer comme `not planned` lorsque :

- la direction d’architecture a changé ;
- l’issue est remplacée par un epic plus récent ;
- le composant est retiré ou archivé ;
- le coût/risque n’est plus justifié.

Ne jamais maintenir une issue `Done` ouverte pour conserver de la documentation. Utiliser une roadmap, une release note ou une page de preuves.

## 9. Politique de labels recommandée

Labels cross-repo minimaux :

- `priority:P0`, `priority:P1`, `priority:P2`, `priority:P3` ;
- `type:security`, `type:refactor`, `type:ci`, `type:build`, `type:docs` ;
- `area:runtime`, `area:p2p`, `area:backend`, `area:frontend`, `area:desktop`, `area:deploy` ;
- `status:blocked`, `status:needs-evidence`, `status:ready` ;
- `breaking-change` ;
- `archive-candidate`.

Éviter d’encoder le statut dans le titre (`[Done]`, `[To Do]`, `[In Progress]`). Le statut doit être porté par l’état, le projet ou le label.

## 10. Preuve d’application

Le runner `.github/scripts/apply_refactor_issue_plan.py` :

- recherche chaque titre exact dans tous les états ;
- crée uniquement les absents ;
- ferme uniquement les issues explicitement listées et encore ouvertes ;
- écrit le résultat sous `docs/audit/generated-issues/`.

Cette idempotence permet de relancer l’opération sans créer de doublons.
