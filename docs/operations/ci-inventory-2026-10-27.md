# Inventaire CI/CD mesuré — 27 octobre 2026

Cette capture actualise le relevé du [26 octobre](ci-inventory-2026-10-26.md) après le retour à l’architecture multi-dépôts. Elle sépare les workflows actifs, les définitions désactivées, les métadonnées GitHub et les anciens runs.

## Portée et méthode

- Métadonnées des workflows, fichiers YAML présents et variables de contrôle : capture **27 octobre 2026 à 22:26 UTC**, chaque source lue au SHA exact de sa branche `main`.
- Historique : au plus **20 derniers runs du workflow principal** par dépôt, capturés à **22:17 UTC** ; Integration n’en avait aucun. Runs et jobs n’ont pas été relancés.
- Métriques Workbench : commande `dev ci metrics --limit 20 --json`, capture à **22:14 UTC** ; échantillon limité aux runs publics du workflow CI Workbench.
- Aucun workflow, build ni test applicatif exécuté pour cette collecte. Les deux exemples de routage ont été calculés directement avec le planificateur commun.

Les durées de workflow incluent l’attente ; la somme des durées de jobs peut dépasser la durée murale, car les jobs parallèles se chevauchent. Les labels de runners privés sont réduits à `self-hosted` ou à des classes GitHub-hosted. Aucun acteur, nom de branche, journal, secret ou source applicative n’est publié.

## Références et échantillons

| Dépôt | Visibilité | SHA `main` observé | Pin courant dans Workbench | Workflows inscrits | Runs observés / disponibles |
|---|---|---|---|---:|---:|
| Workbench | public | `2d8e5e406e2ef2d8ba59c00c7c7ad2418e581a7b` | — | 14 | 20 / 104 |
| BackEnd | private | `46fabfe956ca721d25565491a3e0f9bbd9509a8d` | `a24bab6d1f7607fcdca85b52b690de2b53578558` | 2 | 20 / 63 |
| FrontEnd | private | `69fffec62ee8ca87d9142489a01aa24bb7eb8e13` | `3b5f0975ca0cdbdcff430023214e718401e3e266` | 2 | 20 / 97 |
| DesktopApp | private | `f8b924e61e9b1f35c38257225c6fc2febe1e5217` | `ef12c73350bc630579a9d2c3a56d985a64a871cf` | 2 | 2 / 2 |
| Network | private | `03607d2e7b4842e2c4c48b8e0a6501437488a81f` | `3bc1e3493842ba00adda83650d3ccf762e471421` | 7 | 20 / 198 |
| Solana | private | `a132f86671cb47872781e5eb5c8018f13800321a` | `ef8f07d4fbedf28db01ce258a1988e19e3f13f73` | 1 | 1 / 1 |
| Integration | private | `866c51dfe4d81245ec77504e70132dda3d613669` | — | 1 | 0 / 0 |

## Résumé des runs principaux

Les runs privés ci-dessous sont des historiques de leurs anciennes voies de qualification. Les workflows BackEnd, FrontEnd et Network sont désactivés manuellement au SHA observé ; les résultats ne prouvent pas une qualification actuelle. Les runs `skipped` ne sont pas des validations. Pour les médianes et p95 privés, les runs annulés et ignorés sont exclus, les succès et échecs terminés sont inclus.

| Dépôt / workflow | Échantillon | Conclusions | Runners observés | Médiane / p95 écoulé | Queue médiane / p95 | Jobs observés |
|---|---:|---|---|---:|---:|---:|
| Workbench / CI | 20 | annulé 1, OK 19 | `ubuntu-24.04, unreported, windows-2022` | 2m02s / 4m41s | 0s / 0s | 160 |
| BackEnd / Backend CI | 20 | annulé 1, échec 1, OK 18 | `self-hosted` | 2m26s / 18m08s | 0s / 12m32s | 60 |
| FrontEnd / Frontend CI | 20 | annulé 1, échec 8, OK 11 | `self-hosted, ubuntu-latest` | 4m35s / 8m19s | 0s / 0s | 80 |
| DesktopApp / CI | 2 | ignoré 2 | `unreported` | — / — | — / — | 2 |
| Network / Network CI | 20 | annulé 7, échec 10, OK 3 | `self-hosted, ubuntu-latest` | 30m40s / 2h06m47s | 0s / 2h01m00s | 129 |
| Solana / CI | 1 | ignoré 1 | `unreported` | — / — | — / — | 1 |
| Integration / Full private integration | 0 | aucun run | `—` | — / — | — / — | 0 |

### Mesures détaillées Workbench

| Mesure | Observations | Médiane | p95 |
|---|---:|---:|---:|
| Workflow complet | 19 | 2m02s | 4m41s |
| Attente avant démarrage du workflow | 20 | 0s | 0s |
| Retour des contrôles rapides | 19 | 1m43s | 3m56s |
| Queue / provisionnement des jobs | 133 jobs | 4s | 6s |
| Exécution des jobs | 133 jobs | 23s | 1m10s |

Sur ces 20 runs : **19 réussites, 0 échec et 1 annulation**. La mesure de cache est de **10 hits / 10 misses** (50%) ; 20 rapports ont été lus, aucun n’a été omis par le budget de téléchargement. Les artefacts Workbench totalisent 358 entrées, 812924 octets ; le parcours paginé est complet. Ces volumes ne couvrent pas les dépôts privés.

## Inventaire des workflows inscrits

Les entrées dynamiques de CodeQL, Dependabot et Copilot sont des workflows gérés par GitHub et n’ont pas de YAML dans le dépôt. « YAML absent » désigne une entrée Actions de dépôt dont le chemin n’existe pas au SHA `main` ; elle n’est pas comptée comme une suite qualifiante. `matrix-driven` signale un timeout déterminé par la matrice. `Reusable` indique un workflow déclenchable via `workflow_call`, et `appels` le nombre de workflows réutilisables qu’il appelle.

| Dépôt | Workflow (ID) | État | Source | Runner | Événements | Jobs / Reusable / appels | Filtres chemins | Cache | Concurrence | Timeout (min) | Permissions explicites | Événement privilégié |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Workbench | CI (395760310) | `active` | YAML présent | `dynamic, ubuntu-24.04` | `pull_request, push, workflow_dispatch` | 5 / non / 0 | non | oui | oui | 10, matrix-driven | oui | non |
| Workbench | Complementary qualification (396395447) | `active` | YAML présent | `ubuntu-24.04` | `schedule, workflow_dispatch` | 1 / non / 0 | non | non | oui | 45 | oui | non |
| Workbench | Deploy (396395449) | `active` | YAML présent | `ubuntu-24.04` | `release, workflow_dispatch` | 1 / non / 0 | non | non | oui | 30 | oui | non |
| Workbench | Host diagnostics (396395450) | `active` | YAML présent | `ubuntu-24.04` | `workflow_dispatch` | 1 / non / 0 | non | non | oui | 5 | oui | non |
| Workbench | Project sync (396395452) | `active` | YAML présent | `ubuntu-24.04` | `issues, pull_request_target, schedule, workflow_dispatch, workflow_run` | 1 / non / 0 | non | non | oui | 10 | oui | oui |
| Workbench | Private component qualification (397274546) | `active` | YAML présent | `dynamic, ubuntu-24.04` | `workflow_call` | 3 / oui / 0 | non | non | non | 10, matrix-driven | oui | non |
| Workbench | Verify private Integration evidence (397959870) | `active` | YAML présent | `ubuntu-24.04` | `workflow_call` | 1 / oui / 0 | non | non | non | 10 | oui | non |
| Workbench | CodeQL (398164783) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | Dependency Graph (398164815) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | Full repository audit (322996833) | `disabled_manually` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | Repository audit fast evidence (323001213) | `disabled_manually` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | .github/workflows/apply-refactor-issue-plan.yml (323006168) | `disabled_manually` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | Apply refactor issues from audit PR (323009320) | `disabled_manually` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Workbench | Mirror Epitech (328553570) | `disabled_manually` | YAML présent | `ubuntu-24.04` | `workflow_dispatch, workflow_run` | 1 / non / 0 | non | non | oui | 10 | oui | oui |
| BackEnd | Backend CI (328545691) | `disabled_manually` | YAML présent | `self-hosted` | `pull_request, push, workflow_dispatch` | 3 / non / 0 | non | oui | oui | — | oui | non |
| BackEnd | Copilot cloud agent (366109124) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| FrontEnd | Frontend CI (328545692) | `disabled_manually` | YAML présent | `self-hosted` | `pull_request, push, workflow_dispatch` | 4 / non / 0 | non | non | non | — | non | non |
| FrontEnd | CodeQL (210043907) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| DesktopApp | CI (396740141) | `active` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| DesktopApp | Mirror to Epitech (197145012) | `disabled_manually` | YAML présent | `—` | `push, workflow_dispatch` | 1 / non / 1 | non | non | non | — | non | non |
| Network | Copilot coding agent (253551377) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| Network | CodeQL (315682831) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| Network | Dependency Graph (315877723) | `active` | géré par GitHub | `—` | `—` | — | — | — | — | — | — | — |
| Network | Native Runtime (318063632) | `active` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Network | Create GitHub Release (209004743) | `disabled_manually` | YAML présent | `self-hosted` | `push, workflow_dispatch` | 2 / non / 1 | non | non | non | — | oui | non |
| Network | Network CI (328427375) | `disabled_manually` | YAML présent | `self-hosted` | `pull_request, push, workflow_call, workflow_dispatch` | 6 / oui / 0 | non | oui | oui | 90 | oui | non |
| Network | Solana SBF build (393489356) | `disabled_manually` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Solana | CI (396740156) | `active` | YAML absent | `—` | `—` | — | — | — | — | — | — | — |
| Integration | Full private integration (397292339) | `active` | YAML présent | `dynamic, ubuntu-24.04` | `workflow_dispatch` | 3 / non / 0 | non | non | oui | 10, matrix-driven | oui | non |

### Définitions à traiter explicitement

- BackEnd `Backend CI`, FrontEnd `Frontend CI`, Network `Network CI` et `Create GitHub Release` ont encore leur YAML sur `main` avec `self-hosted`, mais leurs états sont `disabled_manually`. Les drapeaux `SILICIUM_COMPONENT_CI_ENABLED` sont à `0` dans les cinq dépôts composants ; aucune de ces voies ne s’exécute aujourd’hui. Les logs historiques montrent tout de même des runners auto-hébergés.
- Workbench utilise des runners GitHub-hosted pour CI, qualification, Project sync, déploiement et diagnostics ; aucune définition Workbench n’utilise `self-hosted`. Le job CI s’adapte à la matrice et au plan de suite ; le cache est activé uniquement dans la voie CI qualifiée.
- Le déploiement Workbench et les diagnostics sont des opérations GitHub-hosted pouvant accéder au VPS par SSH. `SILICIUM_DELIVERY_ENABLED=0` et `SILICIUM_DIAGNOSTICS_ENABLED=0` ; aucun job n’est en file ou en cours sur les sept dépôts à 22:26 UTC. Aucun build/test sur le VPS n’apparaît dans les workflows actuels.
- Project sync inclut `pull_request_target` et `workflow_run`; le job s’exécute sur `ubuntu-24.04`, vérifie que les PR/runs proviennent de Workbench puis checkout `main` (pas le contenu de la PR). Son jeton App `Workbench/planning-private` lit Actions, checks, contents, deployments, issues et PR ; il peut écrire sur Organization Projects en mode apply. Son jeton Integration lit seulement checks et PR. Ces scopes App s’ajoutent à `contents:read` déclaré pour `GITHUB_TOKEN`. La PR Workbench [#342](https://github.com/Silicium-Project/Workbench/pull/342) ajoute les lectures dédiées aux cinq composants, mais elle n’est pas encore fusionnée. C’est le seul workflow Workbench identifié avec événement privilégié.
- Entrées Actions avec source manquante au SHA observé : DesktopApp `CI` (actif), Network `Native Runtime` (actif), Solana `CI` (actif), Network `Solana SBF build` (désactivé). Workbench a aussi quatre anciennes entrées d’audit désactivées dont les YAML ont disparu. Ces entrées ne sont pas des preuves de qualification.
- Aucun workflow `Release` Workbench n’apparaît dans la liste actuelle à 22:26 UTC. Le fichier a disparu de `main` depuis la capture du 26 octobre.
- Depuis le SHA Workbench de la capture du 26 octobre (`90bec77675ca`), les workflows `campaigns`, `ci`, `component-ci`, `deploy`, `diagnostics`, `mirror-epitech` et `project-sync` ont changé ; `private-integration-evidence.yml` a été ajouté et `release.yml` supprimé. `Integration/qualification.yml` a aussi changé. Les cinq SHAs `main` privés restent ceux indiqués dans la capture précédente.
- Les anciens workflows BackEnd et FrontEnd n’ont pas de `timeout-minutes`; Network en fixe un à 90 min. Aucun n’a de filtre de chemin déclaré au niveau des événements. FrontEnd n’a pas de permissions explicites ; comparer ces règles aux wrappers futurs avant migration.
- L’endpoint org des runners a répondu HTTP 403, faute de permission `admin:org`/runner groups. L’absence d’exécution et la désactivation ne prouvent pas que les runners VPS ont été désenregistrés.

### Dépendances de jobs et références d’accès

La table couvre chaque YAML présent au SHA observé. Une ligne vide signifie qu’aucun `needs` n’est déclaré. Les permissions viennent des blocs `permissions` root/job ; un workflow peut créer un jeton d’App aux scopes différents, précisé dans les notes. « Secret » indique seulement qu’une expression `${{ secrets.* }}` existe ; aucune valeur n’est incluse. « Environment » signale un environnement déclaré, pas la présence vérifiée d’approbateurs. La colonne SSH indique qu’une référence SSH figure dans le fichier, pas que la connexion a été exécutée.

| Dépôt / workflow | Dépendances `needs` | Permissions déclarées | Réf. secret | Environment | Réf. SSH |
|---|---|---|---|---|---|
| Workbench / CI | `changes←budget; validate←changes; required←changes,validate,quick; quick←changes` | `contents:read; pull-requests:read` | oui | oui | non |
| Workbench / Complementary qualification | `—` | `contents:read` | non | non | non |
| Workbench / Deploy | `—` | `actions:read; contents:read; deployments:write` | oui | oui | oui |
| Workbench / Host diagnostics | `—` | `contents:read` | oui | oui | oui |
| Workbench / Project sync | `—` | `contents:read` | oui | oui | non |
| Workbench / Private component qualification | `validate←plan; required←plan,validate` | `actions:read; contents:read; pull-requests:read` | non | non | non |
| Workbench / Verify private Integration evidence | `—` | `actions:read; contents:read` | non | non | non |
| Workbench / Mirror Epitech | `—` | `contents:read` | oui | oui | oui |
| BackEnd / Backend CI | `test←changes; build←changes,test` | `contents:read` | non | non | non |
| FrontEnd / Frontend CI | `unit←changes; build←changes,unit; functional←changes,build` | `non déclarées` | non | non | non |
| DesktopApp / Mirror to Epitech | `—` | `non déclarées` | non | non | non |
| Network / Create GitHub Release | `release←tests` | `contents:write` | oui | non | non |
| Network / Network CI | `codeql←changes; p2p-node←changes; solana-layer←changes; tests←changes; pytest-hosted←changes` | `contents:read; packages:write` | non | non | non |
| Integration / Full private integration | `validate←plan; required←plan,validate` | `actions:read; contents:read` | oui | non | non |

## Variables de contrôle et exécutions actuelles

| Dépôt | Variable | Valeur observée | Effet constaté |
|---|---|---:|---|
| Workbench | `SILICIUM_DELIVERY_ENABLED` | `0` | Désactive le chemin de livraison depuis Workbench. |
| Workbench | `SILICIUM_DIAGNOSTICS_ENABLED` | `0` | Désactive les diagnostics distants. |
| Workbench | `SILICIUM_PROJECT_AUTOMATION_ENABLED` | `1` | Automatisation Project autorisée selon ses contrôles de source et permissions. |
| Workbench | `SILICIUM_WINDOWS_ALLOW_SELF_SIGNED` | `true` | Option de configuration desktop/Windows ; sans lien avec l’activation de la CI. |
| BackEnd | `SILICIUM_COMPONENT_CI_ENABLED` | `0` | Désactive la qualification applicative native de ce dépôt. |
| FrontEnd | `SILICIUM_COMPONENT_CI_ENABLED` | `0` | Désactive la qualification applicative native de ce dépôt. |
| DesktopApp | `SILICIUM_COMPONENT_CI_ENABLED` | `0` | Désactive la qualification applicative native de ce dépôt. |
| Network | `SILICIUM_COMPONENT_CI_ENABLED` | `0` | Désactive la qualification applicative native de ce dépôt. |
| Solana | `SILICIUM_COMPONENT_CI_ENABLED` | `0` | Désactive la qualification applicative native de ce dépôt. |
| Integration | `SILICIUM_INTEGRATION_ENABLED` | `0` | Désactive la qualification privée d’intégration. |

Au relevé de 22:26 UTC, tous les dépôts comptaient **0 run en attente et 0 run en cours**. Le tableau de facturation fourni séparément par le propriétaire indique que le quota de minutes privées est épuisé et que le dépassement est bloqué ; aucun achat, changement de plafond ou runner VPS de secours n’a été effectué.

## Emploi du planificateur commun

Les exemples ont été calculés avec `route()` et les registres de lanes/workspace présents à la capture. Ils expliquent le routage ; ils ne déclenchent aucune suite.

| Changement | Plan public | Qualification Integration |
|---|---|---|
| `docs/operations/ci-inventory-2026-10-27.md` | `full=false`; `docs`, `powershell`, `security`, `tooling` | 15 suites de PR, dont 11 suites applicatives privées différées dans le scope public |
| `contracts/job-v1.json` | Routage conservateur `full=true`, tous les composants affectés ; seules les quatre suites publiques s’exécutent dans Workbench | Les 15 suites de PR sont requises dans Integration |

Un chemin inconnu déclenche également `full=true`. Aucun contrôle obligatoire n’est supprimé pour réduire les minutes.

## PR de migration des composants

Les cinq PR natives de wrappers restent ouvertes en brouillon. Les SHA `main` épinglés sont conservés séparément des SHA de tête de PR ; l’alignement se fait seulement après qualification et revue.

| Dépôt | PR | État | SHA tête actuel | Pin Workbench |
|---|---|---|---|---|
| BackEnd | [#39](https://github.com/Silicium-Project/BackEnd/pull/39) | open, draft | `8bea9a873dd6e94b962516a89a8b8a9285b9a8e8` | `a24bab6d1f7607fcdca85b52b690de2b53578558` |
| FrontEnd | [#28](https://github.com/Silicium-Project/FrontEnd/pull/28) | open, draft | `3b5f0975ca0cdbdcff430023214e718401e3e266` | `3b5f0975ca0cdbdcff430023214e718401e3e266` |
| DesktopApp | [#1](https://github.com/Silicium-Project/DesktopApp/pull/1) | open, draft | `6a233f1c421358143238c25562c45ad607b85721` | `ef12c73350bc630579a9d2c3a56d985a64a871cf` |
| Network | [#355](https://github.com/Silicium-Project/Network/pull/355) | open, draft | `9f75a07ee482bb7f5816c125b3abc4d7bc45b5ee` | `3bc1e3493842ba00adda83650d3ccf762e471421` |
| Solana | [#1](https://github.com/Silicium-Project/Solana/pull/1) | open, draft | `ef8f07d4fbedf28db01ce258a1988e19e3f13f73` | `ef8f07d4fbedf28db01ce258a1988e19e3f13f73` |

## Runs détaillés

Les tables comprennent tous les runs de l’échantillon, au plus 20 par dépôt. La colonne `Jobs Σ` additionne les intervalles des jobs ; elle peut dépasser `Écoulé` lorsque les jobs s’exécutent en parallèle.

### Workbench — CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40591023606](https://github.com/Silicium-Project/Workbench/actions/runs/40591023606) | `f3d796f6348a` | 2026-10-27 21:57Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m33s | 1m41s |
| [40586387219](https://github.com/Silicium-Project/Workbench/actions/runs/40586387219) | `b8ebae3703d9` | 2026-10-27 21:23Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m02s | 1m59s |
| [40559708939](https://github.com/Silicium-Project/Workbench/actions/runs/40559708939) | `25f060f1aacf` | 2026-10-27 18:24Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 5m31s | 3m05s |
| [40556276758](https://github.com/Silicium-Project/Workbench/actions/runs/40556276758) | `cd5484ccc68e` | 2026-10-27 18:02Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 5m24s | 3m51s |
| [40555687049](https://github.com/Silicium-Project/Workbench/actions/runs/40555687049) | `f66bb6b1831a` | 2026-10-27 17:59Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | annulé | 0s | 7m54s | 4m23s |
| [40547854858](https://github.com/Silicium-Project/Workbench/actions/runs/40547854858) | `cf6df861c31f` | 2026-10-27 17:09Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m28s | 2m09s |
| [40542039558](https://github.com/Silicium-Project/Workbench/actions/runs/40542039558) | `2d8e5e406e2e` | 2026-10-27 16:33Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 7m04s | 4m41s |
| [40541200018](https://github.com/Silicium-Project/Workbench/actions/runs/40541200018) | `cc778596fbd5` | 2026-10-27 16:28Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 4m09s | 1m54s |
| [40529720876](https://github.com/Silicium-Project/Workbench/actions/runs/40529720876) | `270e9d9cce44` | 2026-10-27 15:18Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m15s | 2m27s |
| [40528487600](https://github.com/Silicium-Project/Workbench/actions/runs/40528487600) | `70cf53404b6d` | 2026-10-27 15:11Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m40s | 1m37s |
| [40526385926](https://github.com/Silicium-Project/Workbench/actions/runs/40526385926) | `f6c1e15df6b3` | 2026-10-27 14:58Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m23s | 2m15s |
| [40526044425](https://github.com/Silicium-Project/Workbench/actions/runs/40526044425) | `75d41fa1b2dd` | 2026-10-27 14:56Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m38s | 1m46s |
| [40526010940](https://github.com/Silicium-Project/Workbench/actions/runs/40526010940) | `8272297aea69` | 2026-10-27 14:56Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m10s | 2m17s |
| [40525637604](https://github.com/Silicium-Project/Workbench/actions/runs/40525637604) | `ef48ed10b1e2` | 2026-10-27 14:54Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m53s | 2m01s |
| [40525579289](https://github.com/Silicium-Project/Workbench/actions/runs/40525579289) | `3b2b58c22b8d` | 2026-10-27 14:53Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m37s | 2m08s |
| [40525208672](https://github.com/Silicium-Project/Workbench/actions/runs/40525208672) | `c0fd25fd8525` | 2026-10-27 14:51Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m02s | 2m01s |
| [40525130686](https://github.com/Silicium-Project/Workbench/actions/runs/40525130686) | `ad464683b411` | 2026-10-27 14:51Z | `push` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m11s | 2m16s |
| [40522851242](https://github.com/Silicium-Project/Workbench/actions/runs/40522851242) | `250439c3e8cc` | 2026-10-27 14:37Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 3m11s | 2m02s |
| [40520524742](https://github.com/Silicium-Project/Workbench/actions/runs/40520524742) | `125abc7c020e` | 2026-10-27 14:22Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m48s | 1m49s |
| [40519656089](https://github.com/Silicium-Project/Workbench/actions/runs/40519656089) | `77a08de86d95` | 2026-10-27 14:17Z | `pull_request` | `ubuntu-24.04, unreported, windows-2022` | OK | 0s | 2m45s | 1m43s |


### BackEnd — Backend CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137789811](https://github.com/Silicium-Project/BackEnd/actions/runs/40137789811) | `a6951027f62d` | 2026-10-24 22:15Z | `pull_request` | `self-hosted` | annulé | 0s | 12s | 16s |
| [39692312086](https://github.com/Silicium-Project/BackEnd/actions/runs/39692312086) | `35387e8374fe` | 2026-10-21 23:16Z | `push` | `self-hosted` | OK | 0s | 5m26s | 5m35s |
| [39650101334](https://github.com/Silicium-Project/BackEnd/actions/runs/39650101334) | `5ccdde1fffb9` | 2026-10-21 18:09Z | `push` | `self-hosted` | OK | 0s | 5m16s | 5m27s |
| [39645345815](https://github.com/Silicium-Project/BackEnd/actions/runs/39645345815) | `4c9448c69f5b` | 2026-10-21 17:36Z | `push` | `self-hosted` | OK | 12m32s | 5m24s | 18m08s |
| [39627870921](https://github.com/Silicium-Project/BackEnd/actions/runs/39627870921) | `4c8509489cff` | 2026-10-21 15:40Z | `push` | `self-hosted` | OK | 0s | 4m18s | 4m51s |
| [39613996600](https://github.com/Silicium-Project/BackEnd/actions/runs/39613996600) | `97a8d1b3d97a` | 2026-10-21 14:07Z | `push` | `self-hosted` | OK | 0s | 3m47s | 3m57s |
| [39607630020](https://github.com/Silicium-Project/BackEnd/actions/runs/39607630020) | `48d7a24ae31f` | 2026-10-21 13:23Z | `push` | `self-hosted` | échec | 0s | 3m37s | 3m46s |
| [39585909115](https://github.com/Silicium-Project/BackEnd/actions/runs/39585909115) | `7af04577a39e` | 2026-10-21 10:37Z | `push` | `self-hosted` | OK | 0s | 4m18s | 4m27s |
| [39577471794](https://github.com/Silicium-Project/BackEnd/actions/runs/39577471794) | `f4120b43f2d1` | 2026-10-21 09:30Z | `push` | `self-hosted` | OK | 0s | 2m12s | 2m20s |
| [39497828512](https://github.com/Silicium-Project/BackEnd/actions/runs/39497828512) | `c5247f5182ca` | 2026-10-20 21:07Z | `push` | `self-hosted` | OK | 0s | 2m23s | 2m32s |
| [39459948189](https://github.com/Silicium-Project/BackEnd/actions/runs/39459948189) | `c177c02a17cb` | 2026-10-20 16:43Z | `push` | `self-hosted` | OK | 0s | 2m15s | 2m26s |
| [38889990405](https://github.com/Silicium-Project/BackEnd/actions/runs/38889990405) | `1ef3fe3ed5e4` | 2026-10-16 10:51Z | `push` | `self-hosted` | OK | 0s | 2m22s | 2m30s |
| [38600562593](https://github.com/Silicium-Project/BackEnd/actions/runs/38600562593) | `c311dd2ddbdd` | 2026-10-14 16:43Z | `push` | `self-hosted` | OK | 0s | 1m31s | 1m40s |
| [38561405340](https://github.com/Silicium-Project/BackEnd/actions/runs/38561405340) | `c861426971c2` | 2026-10-14 12:06Z | `push` | `self-hosted` | OK | 0s | 1m57s | 2m08s |
| [38419628009](https://github.com/Silicium-Project/BackEnd/actions/runs/38419628009) | `d9b2256be76d` | 2026-10-13 15:09Z | `push` | `self-hosted` | OK | 0s | 1m38s | 1m46s |
| [37833700107](https://github.com/Silicium-Project/BackEnd/actions/runs/37833700107) | `aa3cdbcc37b2` | 2026-10-08 19:40Z | `push` | `self-hosted` | OK | 0s | 1m27s | 1m39s |
| [37777647120](https://github.com/Silicium-Project/BackEnd/actions/runs/37777647120) | `a74607d3005e` | 2026-10-08 12:32Z | `push` | `self-hosted` | OK | 0s | 1m56s | 2m06s |
| [37668723350](https://github.com/Silicium-Project/BackEnd/actions/runs/37668723350) | `5ba236e445b4` | 2026-10-07 18:41Z | `push` | `self-hosted` | OK | 0s | 1m24s | 1m32s |
| [37602649591](https://github.com/Silicium-Project/BackEnd/actions/runs/37602649591) | `a09a663658ca` | 2026-10-07 09:44Z | `push` | `self-hosted` | OK | 0s | 1m45s | 1m55s |
| [37522846074](https://github.com/Silicium-Project/BackEnd/actions/runs/37522846074) | `9012981f6b51` | 2026-10-06 19:58Z | `push` | `self-hosted` | OK | 0s | 1m20s | 1m31s |


### FrontEnd — Frontend CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137798922](https://github.com/Silicium-Project/FrontEnd/actions/runs/40137798922) | `3ad08c48209f` | 2026-10-24 22:15Z | `pull_request` | `self-hosted` | annulé | 0s | 19s | 24s |
| [40109391568](https://github.com/Silicium-Project/FrontEnd/actions/runs/40109391568) | `238de77dc851` | 2026-10-24 15:58Z | `push` | `ubuntu-latest` | OK | 0s | 3m49s | 4m02s |
| [40109272711](https://github.com/Silicium-Project/FrontEnd/actions/runs/40109272711) | `f2bfabc83c49` | 2026-10-24 15:56Z | `push` | `ubuntu-latest` | échec | 0s | 38s | 44s |
| [40106865798](https://github.com/Silicium-Project/FrontEnd/actions/runs/40106865798) | `5b7ef0c840a3` | 2026-10-24 15:25Z | `push` | `ubuntu-latest` | échec | 0s | 38s | 46s |
| [40102138977](https://github.com/Silicium-Project/FrontEnd/actions/runs/40102138977) | `77a86612ecc5` | 2026-10-24 14:21Z | `push` | `ubuntu-latest` | OK | 0s | 4m58s | 5m10s |
| [40098507953](https://github.com/Silicium-Project/FrontEnd/actions/runs/40098507953) | `f5a8731d29b3` | 2026-10-24 13:31Z | `push` | `ubuntu-latest` | OK | 0s | 4m38s | 4m51s |
| [40098111571](https://github.com/Silicium-Project/FrontEnd/actions/runs/40098111571) | `6f9927ad4e16` | 2026-10-24 13:26Z | `push` | `ubuntu-latest` | OK | 0s | 4m08s | 4m21s |
| [40094544524](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094544524) | `b138e7f2cacc` | 2026-10-24 12:35Z | `push` | `ubuntu-latest` | OK | 0s | 4m25s | 4m36s |
| [40094542442](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094542442) | `b138e7f2cacc` | 2026-10-24 12:35Z | `push` | `ubuntu-latest` | OK | 0s | 4m10s | 4m23s |
| [40094138452](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094138452) | `000fcf913d87` | 2026-10-24 12:29Z | `push` | `ubuntu-latest` | échec | 0s | 4m57s | 5m10s |
| [40094136595](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094136595) | `000fcf913d87` | 2026-10-24 12:29Z | `push` | `ubuntu-latest` | échec | 0s | 4m24s | 4m35s |
| [40093938723](https://github.com/Silicium-Project/FrontEnd/actions/runs/40093938723) | `155bfd75696c` | 2026-10-24 12:26Z | `push` | `ubuntu-latest` | OK | 0s | 3m45s | 3m57s |
| [40093855122](https://github.com/Silicium-Project/FrontEnd/actions/runs/40093855122) | `155bfd75696c` | 2026-10-24 12:25Z | `push` | `ubuntu-latest` | OK | 0s | 5m01s | 5m13s |
| [40091128073](https://github.com/Silicium-Project/FrontEnd/actions/runs/40091128073) | `8bf551075df4` | 2026-10-24 11:44Z | `push` | `ubuntu-latest` | OK | 0s | 4m37s | 4m49s |
| [40084334196](https://github.com/Silicium-Project/FrontEnd/actions/runs/40084334196) | `f78b7e233f0d` | 2026-10-24 10:02Z | `push` | `ubuntu-latest` | échec | 0s | 4m53s | 5m06s |
| [40083869211](https://github.com/Silicium-Project/FrontEnd/actions/runs/40083869211) | `f78b7e233f0d` | 2026-10-24 09:55Z | `push` | `ubuntu-latest` | OK | 0s | 5m19s | 5m34s |
| [40083594986](https://github.com/Silicium-Project/FrontEnd/actions/runs/40083594986) | `cae4e209ca18` | 2026-10-24 09:51Z | `push` | `ubuntu-latest` | OK | 0s | 4m03s | 4m15s |
| [40082774896](https://github.com/Silicium-Project/FrontEnd/actions/runs/40082774896) | `30f85c54e029` | 2026-10-24 09:38Z | `push` | `ubuntu-latest` | échec | 0s | 8m04s | 8m19s |
| [40082299462](https://github.com/Silicium-Project/FrontEnd/actions/runs/40082299462) | `ba853f258931` | 2026-10-24 09:31Z | `push` | `ubuntu-latest` | échec | 0s | 1m20s | 1m31s |
| [40081892350](https://github.com/Silicium-Project/FrontEnd/actions/runs/40081892350) | `750bd01f53d7` | 2026-10-24 09:25Z | `push` | `ubuntu-latest` | échec | 0s | 1m31s | 1m42s |


### DesktopApp — CI (2 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40408858132](https://github.com/Silicium-Project/DesktopApp/actions/runs/40408858132) | `6a233f1c4213` | 2026-10-26 21:59Z | `pull_request` | `unreported` | ignoré | 0s | 0s | 1s |
| [40283448257](https://github.com/Silicium-Project/DesktopApp/actions/runs/40283448257) | `ef12c73350bc` | 2026-10-26 07:03Z | `pull_request` | `unreported` | ignoré | 0s | 0s | 1s |


### Network — Network CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137778682](https://github.com/Silicium-Project/Network/actions/runs/40137778682) | `d2ffdcef04d4` | 2026-10-24 22:15Z | `pull_request` | `self-hosted` | annulé | 0s | 3m34s | 1m37s |
| [40086109149](https://github.com/Silicium-Project/Network/actions/runs/40086109149) | `e2eb8f109d91` | 2026-10-24 10:29Z | `push` | `ubuntu-latest` | échec | 0s | 39m03s | 38m51s |
| [40085504064](https://github.com/Silicium-Project/Network/actions/runs/40085504064) | `e2eb8f109d91` | 2026-10-24 10:20Z | `push` | `ubuntu-latest` | OK | 0s | 8m11s | 8m23s |
| [40083714983](https://github.com/Silicium-Project/Network/actions/runs/40083714983) | `f364c9e3be48` | 2026-10-24 09:53Z | `push` | `ubuntu-latest` | échec | 0s | 18m56s | 19m43s |
| [40083274752](https://github.com/Silicium-Project/Network/actions/runs/40083274752) | `2f2826bed4e7` | 2026-10-24 09:46Z | `push` | `ubuntu-latest` | annulé | 0s | 7m10s | 7m21s |
| [40080804120](https://github.com/Silicium-Project/Network/actions/runs/40080804120) | `d845688dc72f` | 2026-10-24 09:08Z | `push` | `ubuntu-latest` | échec | 0s | 34m05s | 33m59s |
| [39859547458](https://github.com/Silicium-Project/Network/actions/runs/39859547458) | `6f8da5509252` | 2026-10-22 21:43Z | `push` | `self-hosted` | annulé | 0s | 16m06s | 18m09s |
| [39857483928](https://github.com/Silicium-Project/Network/actions/runs/39857483928) | `68e0615e7a6f` | 2026-10-22 21:28Z | `push` | `self-hosted` | annulé | 0s | 17m09s | 17m20s |
| [39854164892](https://github.com/Silicium-Project/Network/actions/runs/39854164892) | `5f3f604cd90f` | 2026-10-22 21:03Z | `push` | `self-hosted` | échec | 0s | 19m07s | 19m19s |
| [39840270863](https://github.com/Silicium-Project/Network/actions/runs/39840270863) | `05d148c4e609` | 2026-10-22 19:27Z | `push` | `self-hosted` | échec | 0s | 1h20m52s | 1h19m08s |
| [39789219448](https://github.com/Silicium-Project/Network/actions/runs/39789219448) | `7d94cf68a07e` | 2026-10-22 13:42Z | `push` | `self-hosted` | échec | 2h01m00s | 1h39m23s | 2h06m47s |
| [39770909656](https://github.com/Silicium-Project/Network/actions/runs/39770909656) | `f73efa66c90a` | 2026-10-22 11:29Z | `push` | `self-hosted` | échec | 0s | 1h24m01s | 51m15s |
| [39730723790](https://github.com/Silicium-Project/Network/actions/runs/39730723790) | `023c038d5156` | 2026-10-22 05:54Z | `push` | `self-hosted` | annulé | 0s | 12m55s | 5m46s |
| [39730186339](https://github.com/Silicium-Project/Network/actions/runs/39730186339) | `c0143f906499` | 2026-10-22 05:49Z | `push` | `self-hosted` | annulé | 0s | 18m21s | 6m41s |
| [39721338746](https://github.com/Silicium-Project/Network/actions/runs/39721338746) | `fd540611322a` | 2026-10-22 04:15Z | `push` | `self-hosted` | échec | 0s | 35m29s | 30m40s |
| [39719577042](https://github.com/Silicium-Project/Network/actions/runs/39719577042) | `6ce340996d2f` | 2026-10-22 03:56Z | `push` | `self-hosted` | OK | 0s | 13m39s | 7m51s |
| [39696747154](https://github.com/Silicium-Project/Network/actions/runs/39696747154) | `c379ef907793` | 2026-10-21 23:57Z | `push` | `self-hosted` | OK | 19m42s | 30m56s | 28m29s |
| [39693051822](https://github.com/Silicium-Project/Network/actions/runs/39693051822) | `80644ba93b88` | 2026-10-21 23:23Z | `push` | `self-hosted` | annulé | 21m44s | 22m39s | 35m31s |
| [39673528005](https://github.com/Silicium-Project/Network/actions/runs/39673528005) | `2891961b5f7d` | 2026-10-21 20:48Z | `push` | `self-hosted` | échec | 0s | 3h03m01s | 1h46m19s |
| [39666925019](https://github.com/Silicium-Project/Network/actions/runs/39666925019) | `ccc5a991b8c3` | 2026-10-21 20:03Z | `push` | `self-hosted` | échec | 0s | 16m24s | 15m15s |


### Solana — CI (1 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Attente | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40283450884](https://github.com/Silicium-Project/Solana/actions/runs/40283450884) | `ef8f07d4fbed` | 2026-10-26 07:03Z | `pull_request` | `unreported` | ignoré | 0s | 0s | 1s |


### Integration — Full private integration (0 run(s))

Aucun run dans l’échantillon.


## Suites suivantes proposées

1. **CI-01** : migrer les voies natives vers des runners GitHub-hosted, en s’appuyant sur les résultats de PR wrappers ; conserver toute suite obligatoire et comparer les preuves avant de mettre à jour les pins. Ne réactiver aucun flag avant le retour du quota inclus ou une nouvelle décision de budget.
2. **CI-02** : optimiser à partir des distributions observées : annuler les validations remplacées, réduire les tâches dupliquées seulement après preuve d’équivalence, analyser le p95 Network auto-hébergé historique et définir un timeout de job explicite pour toutes les suites. Garder les obligations sécurité et le gate final.
3. **Gouvernance runner** : obtenir le droit de lecture org `runners` pour vérifier le désenregistrement ; ne pas le déduire de l’état des workflows.
4. **Nettoyage de l’inventaire Actions** : examiner avec les propriétaires les entrées source manquante, puis les supprimer ou restaurer leur YAML dans une tranche séparée ; aucune entrée n’a été modifiée ici.
5. **Qualification privée** : vérifier les cinq wrappers, l’Integration et les rapports avant toute livraison ; une CI Workbench publique verte ne qualifie pas les applications.

## Limites et validation de cette tranche

- Capture GitHub REST read-only horodatée et liée aux SHA précis en tête de ce rapport et dans le JSON joint.
- Les workflows dynamiques GitHub sont distingués des YAML manquants. La liste des workflows, variables, runs et jobs a été recoupée à travers les réponses API conservées localement.
- Planificateur commun interrogé sur une modification documentaire et un contrat intercomposants ; aucune suite de tests ni construction n’a été lancée.
- Le quota et la facturation proviennent d’une capture fournie par le propriétaire, pas de l’API de cette collecte.
- Aucun secret, droit, protection, flag, workflow ou runner n’a été modifié ; aucune livraison n’a été demandée.
