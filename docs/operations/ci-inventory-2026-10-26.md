# Inventaire CI/CD observé — 26 octobre 2026

Instantané : **2026-10-26T19:09:09+01:00**. Rapport en lecture seule, accompagné des données API expurgées dans [`ci-inventory-2026-10-26.json`](ci-inventory-2026-10-26.json).

## Périmètre et méthode

L’issue [Workbench #241](https://github.com/Silicium-Project/Workbench/issues/241) a été écrite avant le retour à des dépôts séparés. L’instantané actuel couvre donc **Workbench, les cinq dépôts composants privés et Integration**. Les sources sont les branches par défaut, l’API Actions et les jobs récents ; aucun run n’a été relancé et aucune source applicative ni aucun log brut n’a été copié.

Le temps écoulé d’un run est `updated_at - created_at` et inclut l’attente. L’attente indiquée est `run_started_at - created_at`. La somme des durées des jobs n’est pas du temps mural car les jobs peuvent s’exécuter en parallèle. Les percentiles utilisent la règle nearest-rank et doivent toujours être lus avec leur taille d’échantillon.

Les cinq pins Workbench correspondent à des commits présents dans des PR de migration encore en brouillon. Ils ne prouvent ni fusion ni qualification. Les clés d’App et leurs valeurs ne sont pas dans le rapport ; seule leur présence par nom est contrôlée.

## État actuel

| Dépôt | Visibilité | SHA de `main` observé | Pin Workbench | Workflow principal | Runs observés |
|---|---|---|---|---|---:|
| Workbench | public | `90bec77675ca7a67c7202126386ef5dd9033b761` | — | CI | 20 |
| BackEnd | private | `46fabfe956ca721d25565491a3e0f9bbd9509a8d` | `a24bab6d1f7607fcdca85b52b690de2b53578558` | Backend CI | 20 |
| FrontEnd | private | `69fffec62ee8ca87d9142489a01aa24bb7eb8e13` | `3b5f0975ca0cdbdcff430023214e718401e3e266` | Frontend CI | 20 |
| DesktopApp | private | `f8b924e61e9b1f35c38257225c6fc2febe1e5217` | `ef12c73350bc630579a9d2c3a56d985a64a871cf` | CI | 1 |
| Network | private | `03607d2e7b4842e2c4c48b8e0a6501437488a81f` | `3bc1e3493842ba00adda83650d3ccf762e471421` | Network CI | 18 |
| Solana | private | `a132f86671cb47872781e5eb5c8018f13800321a` | `ef8f07d4fbedf28db01ce258a1988e19e3f13f73` | CI | 1 |
| Integration | private | `5ccf81c6e2aa5361706be5c497b1f239c11a3fff` | — | Full private integration | 0 |

**Qualification privée arrêtée :** `SILICIUM_COMPONENT_CI_ENABLED=0` est vérifié dans les cinq dépôts composants. `SILICIUM_INTEGRATION_ENABLED` est absent. Les secrets `SOURCE_APP_CLIENT_ID` et `SOURCE_APP_PRIVATE_KEY` existent dans Integration, vérifiés par nom uniquement. Aucun run Integration n’est enregistré. Le propriétaire a indiqué que le quota inclus Actions privé est épuisé et que tout dépassement est bloqué.

**Aucun travail CI n’est actuellement en attente ou en cours** dans les sept dépôts lors de la vérification. Cela confirme l’absence de queue Actions au moment de la capture ; ce n’est pas une preuve que les runners auto-hébergés ont été désenregistrés. L’API de liste des runners d’organisation a répondu `403` faute de permission `admin:org`.

Les flags Workbench `SILICIUM_DELIVERY_ENABLED`, `SILICIUM_DIAGNOSTICS_ENABLED` et `SILICIUM_PROJECT_AUTOMATION_ENABLED` sont à `0`. Les workflows peuvent donc apparaître « actifs » dans l’interface GitHub tout en étant bloqués par leurs conditions. Les workflows `Deploy`, signatures et qualification privée n’ont pas tourné dans cet instantané ; aucune publication récente n’a été observée. Le miroir Epitech n’a qu’un run ancien, mentionné plus bas.

## Pipeline public mesuré

Le run GitHub `./dev ci metrics --limit 20 --json`, lu au même instant, observe 20 runs CI Workbench : **10 succès, 9 échecs, 1 annulation**. Il distingue les jobs de validation publics des suites applicatives différées. Les métriques sont :

| Mesure Workbench CI | Échantillon | Médiane | p95 |
|---|---:|---:|---:|
| Workflow complet, runs non annulés | 19 | 2m11s | 8h53m16s |
| Retour des voies rapides | 14 | 1m50s | 8h53m06s |
| Attente / provisionnement des jobs | 158 jobs | 4s | 1m36s |
| Exécution des jobs | 158 jobs | 26s | 6m20s |

Le p95 du workflow est dominé par le run [40284157049](https://github.com/Silicium-Project/Workbench/actions/runs/40284157049) : **8 h 51 min d’attente avant le démarrage**, puis environ 1 min 45 s d’exécution ; le run finit en échec sur les suites `docs`/`tooling` et le gate. L’API ne permet pas d’établir pourquoi GitHub a maintenu ce run en queue. Il ne faut donc pas interpréter ce p95 comme une durée de calcul habituelle. Les trois derniers runs CI réussis observés ont duré 126 à 136 s.

Le relevé des artefacts a trouvé 100 entrées sur 100 listées, pour 579 712 octets. Les rapports de cache exploitables indiquent 24 hits et 16 misses (ratio 60 %) ; **8 runs n’ont pas fourni de preuve de cache**. Les absences ne sont pas comptées comme misses.

## Workflows recensés au SHA par défaut

Le statut `active` ci-dessous décrit l’enregistrement GitHub, pas une autorisation effective de déployer. Les workflows sans fichier au SHA de `main` sont signalés ; plusieurs enregistrements Actions survivent au retrait de leur YAML. `dynamic/…` désigne un workflow géré par GitHub.

| Dépôt | Workflow (ID) | État Actions | Source sur `main` | Runners déclarés (labels privés omis) |
|---|---|---|---|---|
| Workbench | CI (`395760310`) | active | présente | `ubuntu-24.04, ${{ matrix.runner }}` |
| Workbench | Complementary qualification (`396395447`) | active | présente | `ubuntu-24.04` |
| Workbench | Deploy (`396395449`) | active | présente | `ubuntu-24.04` |
| Workbench | Host diagnostics (`396395450`) | active | présente | `ubuntu-24.04` |
| Workbench | Project sync (`396395452`) | active | présente | `ubuntu-24.04` |
| Workbench | Release (`396395453`) | active | présente | `ubuntu-24.04, ${{ matrix.os }}, windows-2022` |
| Workbench | Private component qualification (`397274546`) | active | présente | `ubuntu-24.04, ${{ matrix.runner }}` |
| Workbench | Full repository audit (`322996833`) | disabled_manually | absente à ce SHA | `—` |
| Workbench | Repository audit fast evidence (`323001213`) | disabled_manually | absente à ce SHA | `—` |
| Workbench | .github/workflows/apply-refactor-issue-plan.yml (`323006168`) | disabled_manually | absente à ce SHA | `—` |
| Workbench | Apply refactor issues from audit PR (`323009320`) | disabled_manually | absente à ce SHA | `—` |
| Workbench | Mirror Epitech (`328553570`) | disabled_manually | présente | `ubuntu-24.04` |
| BackEnd | Backend CI (`328545691`) | disabled_manually | présente | `self-hosted` |
| BackEnd | Copilot cloud agent (`366109124`) | active | GitHub-managed | `—` |
| FrontEnd | Frontend CI (`328545692`) | disabled_manually | présente | `self-hosted` |
| FrontEnd | CodeQL (`210043907`) | active | GitHub-managed | `—` |
| DesktopApp | CI (`396740141`) | active | absente à ce SHA | `—` |
| DesktopApp | Mirror to Epitech (`197145012`) | disabled_manually | présente | `—` |
| Network | Copilot coding agent (`253551377`) | active | GitHub-managed | `—` |
| Network | CodeQL (`315682831`) | active | GitHub-managed | `—` |
| Network | Dependency Graph (`315877723`) | active | GitHub-managed | `—` |
| Network | Native Runtime (`318063632`) | active | absente à ce SHA | `—` |
| Network | Create GitHub Release (`209004743`) | disabled_manually | présente | `self-hosted` |
| Network | Network CI (`328427375`) | disabled_manually | présente | `self-hosted` |
| Network | Solana SBF build (`393489356`) | disabled_manually | absente à ce SHA | `—` |
| Solana | CI (`396740156`) | active | absente à ce SHA | `—` |
| Integration | Full private integration (`397292339`) | active | présente | `ubuntu-24.04, ${{ matrix.runner }}` |

### Métriques des anciennes voies CI privées

Ces statistiques portent sur les derniers runs historiques avant suspension ; elles ne décrivent pas une CI privée actuellement active. La médiane et le p95 utilisent les runs terminés non annulés. Le p95 est un indicateur de latence observée, pas un objectif garanti.

| Dépôt / workflow | Runs observés | Résultats | Médiane écoulée | p95 écoulé | p95 attente run |
|---|---:|---|---:|---:|---:|
| Workbench / CI | 20 | 10 OK, 9 échecs, 1 annulation | 2m11s | 8h53m16s | 8h51m31s |
| BackEnd / Backend CI | 20 | 18 OK, 1 échec, 1 annulation | 2m26s | 18m08s | 12m32s |
| FrontEnd / Frontend CI | 20 | 11 OK, 8 échecs, 1 annulation | 4m35s | 8m19s | 0s observé |
| Network / Network CI | 18 | 3 OK, 8 échecs, 7 annulations | 30m40s | 2h06m47s | 2h01m00s |
| DesktopApp / CI | 1 | ignoré | non pertinent | non pertinent | non pertinent |
| Solana / CI | 1 | ignoré | non pertinent | non pertinent | non pertinent |
| Integration / Full private integration | 0 | aucun run | — | — | — |

Les valeurs Network incluent des runs annulés exclus du calcul de médiane/p95 ; la queue de 2h01m vient d’un run auto-hébergé. Les runs DesktopApp et Solana ont été ignorés à cause des flags à zéro : une durée d’une seconde n’est pas une mesure d’exécution.

Les définitions encore présentes sur les `main` privés indiquaient un runner auto-hébergé (label privé omis) pour `Backend CI`, `Frontend CI`, `Network CI` et `Create GitHub Release`. Ces workflows ont depuis été **désactivés manuellement**. Les historiques donnent la distinction suivante :

- BackEnd : 20/20 runs observés sur `self-hosted`. Les jobs définissent une suite de tests Go et une construction de binaires.
- FrontEnd : 1/20 run sur `self-hosted`, 19/20 sur `ubuntu-latest` dans l’échantillon historique ; le YAML au SHA `main` déclare toujours `self-hosted`. Les jobs séparent tests unitaires, construction Nuxt et tests fonctionnels.
- Network : 13/18 runs `Network CI` sur `self-hosted` et 5/18 sur `ubuntu-latest`. Le YAML au SHA `main` déclare `self-hosted` pour `p2p-node`, `solana-layer`, `tests` et `pytest-hosted`.
- Le job Network `pytest-hosted` est en réalité sur `self-hosted`. Les jobs `tests` et `pytest-hosted` ont tous deux une étape qui annonce la suite `silicium` : candidat à une déduplication, à confirmer en comparant les arguments, rapports et couvertures avant toute suppression.
- `Network CI.solana-layer` construit le programme Anchor et lance les tests localnet. Un enregistrement historique séparé `Solana SBF build` apparaît aussi, mais son YAML est absent du `main` actuel ; ses runs ont utilisé un runner GitHub. Cela suggère un chevauchement de build, pas une duplication prouvée du même artefact. Les contrôles restent suspendus jusqu’à qualification de la suite commune.
- La publication `Create GitHub Release` est également suspendue. Elle n’est pas un déploiement de service sur le VPS : elle exécutait des tests et préparait une release depuis le runner auto-hébergé.
- `Deploy` et `Host diagnostics` sont définis dans Workbench sur des runners GitHub ; ils peuvent contacter le VPS par SSH, mais ne compilent pas sur le VPS. Leurs flags sont à zéro ; aucun run de déploiement n’a été observé ici.
- Le dernier run DesktopApp du workflow `Mirror to Epitech` visible dans l’échantillon global a attendu environ **19 jours et 20 heures** avant le démarrage, puis s’est terminé. Ce workflow n’est pas une qualification applicative et est désactivé ; cette attente ne doit pas entrer dans les métriques CI produit.

Des répétitions de SHA apparaissent dans les historiques : quatre paires FrontEnd (par ex. `b138e7f2cacc` : runs `40094544524` et `40094542442`) et une paire Network (`e2eb8f109d91` : `40086109149` et `40085504064`). Les deux branches déclenchent une CI `push` sur le même arbre. Le run Workbench `40356369757` et le run `40355853257` partagent aussi le SHA `0614e41cd73d`, mais l’un est `workflow_dispatch` et l’autre une tentative PR relancée (`run_attempt=2`) : ce n’est pas une déduplication démontrée. Il faut garder ces cas candidats et vérifier l’équivalence des obligations avant de fusionner ou supprimer des voies.

Les workflows BackEnd, FrontEnd et Network acceptent plusieurs événements (`push`, `pull_request`, parfois `workflow_dispatch`/`workflow_call`). Les filtres de chemins et la clé de concurrence doivent être revus dans les PR de migration ; aucune obligation sécurité ne doit disparaître pour réduire les minutes.

## Échantillons de runs

Chaque dépôt ci-dessous présente au plus les 20 runs récents de sa voie principale. Les runs `skipped` ne constituent pas une qualification. Les colonnes `jobs Σ` additionnent les intervalles de jobs observés ; elles peuvent dépasser le temps écoulé lorsque les jobs sont parallèles.

### Workbench — CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40370826132](https://github.com/Silicium-Project/Workbench/actions/runs/40370826132) | `006e40747d03` | 2026-10-26 17:40Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 3m19s | 2m11s |
| [40367808786](https://github.com/Silicium-Project/Workbench/actions/runs/40367808786) | `5b8e43c56cab` | 2026-10-26 17:21Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 3m14s | 2m06s |
| [40359090517](https://github.com/Silicium-Project/Workbench/actions/runs/40359090517) | `90bec77675ca` | 2026-10-26 16:26Z | push | `ubuntu-24.04, windows-2022` | OK | 0s | 3m04s | 2m16s |
| [40358697680](https://github.com/Silicium-Project/Workbench/actions/runs/40358697680) | `434da6c83aeb` | 2026-10-26 16:23Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 2m51s | 1m52s |
| [40357338511](https://github.com/Silicium-Project/Workbench/actions/runs/40357338511) | `78b69feea6f3` | 2026-10-26 16:15Z | push | `ubuntu-24.04` | échec | 0s | 39s | 5m54s |
| [40356907373](https://github.com/Silicium-Project/Workbench/actions/runs/40356907373) | `cc3c98e7c007` | 2026-10-26 16:12Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 2m52s | 2m00s |
| [40356369757](https://github.com/Silicium-Project/Workbench/actions/runs/40356369757) | `0614e41cd73d` | 2026-10-26 16:09Z | workflow_dispatch | `ubuntu-24.04, windows-2022` | OK | 0s | 3m07s | 1m58s |
| [40355853257](https://github.com/Silicium-Project/Workbench/actions/runs/40355853257) | `0614e41cd73d` | 2026-10-26 16:06Z | pull_request | `ubuntu-24.04` | échec | 1m14s | 28s | 1m56s |
| [40284157049](https://github.com/Silicium-Project/Workbench/actions/runs/40284157049) | `fe24e51b643d` | 2026-10-26 07:10Z | pull_request | `ubuntu-24.04, windows-2022` | échec | 8h51m31s | 2m43s | 8h53m16s |
| [40283233161](https://github.com/Silicium-Project/Workbench/actions/runs/40283233161) | `2f3e6c8792ea` | 2026-10-26 07:01Z | pull_request | `ubuntu-24.04` | échec | 0s | 27s | 39s |
| [40235140866](https://github.com/Silicium-Project/Workbench/actions/runs/40235140866) | `ff14db3c666e` | 2026-10-25 21:21Z | push | `ubuntu-24.04, windows-2022` | OK | 0s | 3m15s | 2m12s |
| [40234928850](https://github.com/Silicium-Project/Workbench/actions/runs/40234928850) | `873ed2f2156a` | 2026-10-25 21:19Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 2m51s | 1m45s |
| [40232356923](https://github.com/Silicium-Project/Workbench/actions/runs/40232356923) | `24c7590c02ee` | 2026-10-25 20:46Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 29m00s | 15m30s |
| [40223122663](https://github.com/Silicium-Project/Workbench/actions/runs/40223122663) | `03e62285bb7c` | 2026-10-25 18:50Z | pull_request | `ubuntu-24.04, windows-2022` | OK | 0s | 28m28s | 17m04s |
| [40222030783](https://github.com/Silicium-Project/Workbench/actions/runs/40222030783) | `7a57610c148b` | 2026-10-25 18:36Z | pull_request | `ubuntu-24.04, windows-2022` | annulé | 0s | 46m50s | 15m33s |
| [40199389136](https://github.com/Silicium-Project/Workbench/actions/runs/40199389136) | `c04445eb356e` | 2026-10-25 13:49Z | pull_request | `—` | échec | 0s | 9s | 10s |
| [40197099773](https://github.com/Silicium-Project/Workbench/actions/runs/40197099773) | `eadfe01e8fee` | 2026-10-25 13:19Z | pull_request | `ubuntu-24.04, windows-2022` | échec | 0s | 54m48s | 15m40s |
| [40179208684](https://github.com/Silicium-Project/Workbench/actions/runs/40179208684) | `4838ca39e014` | 2026-10-25 09:05Z | pull_request | `ubuntu-24.04, windows-2022` | échec | 0s | 21m05s | 12m09s |
| [40176267805](https://github.com/Silicium-Project/Workbench/actions/runs/40176267805) | `6e42de155f47` | 2026-10-25 08:21Z | pull_request | `ubuntu-24.04, windows-2022` | échec | 0s | 46m46s | 14m18s |
| [40176010077](https://github.com/Silicium-Project/Workbench/actions/runs/40176010077) | `61024725b449` | 2026-10-25 08:17Z | pull_request | `ubuntu-24.04` | échec | 0s | 11s | 19s |

### BackEnd — Backend CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137789811](https://github.com/Silicium-Project/BackEnd/actions/runs/40137789811) | `a6951027f62d` | 2026-10-24 22:15Z | pull_request | `self-hosted` | annulé | 0s | 12s | 16s |
| [39692312086](https://github.com/Silicium-Project/BackEnd/actions/runs/39692312086) | `35387e8374fe` | 2026-10-21 23:16Z | push | `self-hosted` | OK | 0s | 5m26s | 5m35s |
| [39650101334](https://github.com/Silicium-Project/BackEnd/actions/runs/39650101334) | `5ccdde1fffb9` | 2026-10-21 18:09Z | push | `self-hosted` | OK | 0s | 5m16s | 5m27s |
| [39645345815](https://github.com/Silicium-Project/BackEnd/actions/runs/39645345815) | `4c9448c69f5b` | 2026-10-21 17:36Z | push | `self-hosted` | OK | 12m32s | 5m24s | 18m08s |
| [39627870921](https://github.com/Silicium-Project/BackEnd/actions/runs/39627870921) | `4c8509489cff` | 2026-10-21 15:40Z | push | `self-hosted` | OK | 0s | 4m18s | 4m51s |
| [39613996600](https://github.com/Silicium-Project/BackEnd/actions/runs/39613996600) | `97a8d1b3d97a` | 2026-10-21 14:07Z | push | `self-hosted` | OK | 0s | 3m47s | 3m57s |
| [39607630020](https://github.com/Silicium-Project/BackEnd/actions/runs/39607630020) | `48d7a24ae31f` | 2026-10-21 13:23Z | push | `self-hosted` | échec | 0s | 3m37s | 3m46s |
| [39585909115](https://github.com/Silicium-Project/BackEnd/actions/runs/39585909115) | `7af04577a39e` | 2026-10-21 10:37Z | push | `self-hosted` | OK | 0s | 4m18s | 4m27s |
| [39577471794](https://github.com/Silicium-Project/BackEnd/actions/runs/39577471794) | `f4120b43f2d1` | 2026-10-21 09:30Z | push | `self-hosted` | OK | 0s | 2m12s | 2m20s |
| [39497828512](https://github.com/Silicium-Project/BackEnd/actions/runs/39497828512) | `c5247f5182ca` | 2026-10-20 21:07Z | push | `self-hosted` | OK | 0s | 2m23s | 2m32s |
| [39459948189](https://github.com/Silicium-Project/BackEnd/actions/runs/39459948189) | `c177c02a17cb` | 2026-10-20 16:43Z | push | `self-hosted` | OK | 0s | 2m15s | 2m26s |
| [38889990405](https://github.com/Silicium-Project/BackEnd/actions/runs/38889990405) | `1ef3fe3ed5e4` | 2026-10-16 10:51Z | push | `self-hosted` | OK | 0s | 2m22s | 2m30s |
| [38600562593](https://github.com/Silicium-Project/BackEnd/actions/runs/38600562593) | `c311dd2ddbdd` | 2026-10-14 16:43Z | push | `self-hosted` | OK | 0s | 1m31s | 1m40s |
| [38561405340](https://github.com/Silicium-Project/BackEnd/actions/runs/38561405340) | `c861426971c2` | 2026-10-14 12:06Z | push | `self-hosted` | OK | 0s | 1m57s | 2m08s |
| [38419628009](https://github.com/Silicium-Project/BackEnd/actions/runs/38419628009) | `d9b2256be76d` | 2026-10-13 15:09Z | push | `self-hosted` | OK | 0s | 1m38s | 1m46s |
| [37833700107](https://github.com/Silicium-Project/BackEnd/actions/runs/37833700107) | `aa3cdbcc37b2` | 2026-10-08 19:40Z | push | `self-hosted` | OK | 0s | 1m27s | 1m39s |
| [37777647120](https://github.com/Silicium-Project/BackEnd/actions/runs/37777647120) | `a74607d3005e` | 2026-10-08 12:32Z | push | `self-hosted` | OK | 0s | 1m56s | 2m06s |
| [37668723350](https://github.com/Silicium-Project/BackEnd/actions/runs/37668723350) | `5ba236e445b4` | 2026-10-07 18:41Z | push | `self-hosted` | OK | 0s | 1m24s | 1m32s |
| [37602649591](https://github.com/Silicium-Project/BackEnd/actions/runs/37602649591) | `a09a663658ca` | 2026-10-07 09:44Z | push | `self-hosted` | OK | 0s | 1m45s | 1m55s |
| [37522846074](https://github.com/Silicium-Project/BackEnd/actions/runs/37522846074) | `9012981f6b51` | 2026-10-06 19:58Z | push | `self-hosted` | OK | 0s | 1m20s | 1m31s |

### FrontEnd — Frontend CI (20 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137798922](https://github.com/Silicium-Project/FrontEnd/actions/runs/40137798922) | `3ad08c48209f` | 2026-10-24 22:15Z | pull_request | `self-hosted` | annulé | 0s | 19s | 24s |
| [40109391568](https://github.com/Silicium-Project/FrontEnd/actions/runs/40109391568) | `238de77dc851` | 2026-10-24 15:58Z | push | `ubuntu-latest` | OK | 0s | 3m49s | 4m02s |
| [40109272711](https://github.com/Silicium-Project/FrontEnd/actions/runs/40109272711) | `f2bfabc83c49` | 2026-10-24 15:56Z | push | `ubuntu-latest` | échec | 0s | 38s | 44s |
| [40106865798](https://github.com/Silicium-Project/FrontEnd/actions/runs/40106865798) | `5b7ef0c840a3` | 2026-10-24 15:25Z | push | `ubuntu-latest` | échec | 0s | 38s | 46s |
| [40102138977](https://github.com/Silicium-Project/FrontEnd/actions/runs/40102138977) | `77a86612ecc5` | 2026-10-24 14:21Z | push | `ubuntu-latest` | OK | 0s | 4m58s | 5m10s |
| [40098507953](https://github.com/Silicium-Project/FrontEnd/actions/runs/40098507953) | `f5a8731d29b3` | 2026-10-24 13:31Z | push | `ubuntu-latest` | OK | 0s | 4m38s | 4m51s |
| [40098111571](https://github.com/Silicium-Project/FrontEnd/actions/runs/40098111571) | `6f9927ad4e16` | 2026-10-24 13:26Z | push | `ubuntu-latest` | OK | 0s | 4m08s | 4m21s |
| [40094544524](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094544524) | `b138e7f2cacc` | 2026-10-24 12:35Z | push | `ubuntu-latest` | OK | 0s | 4m25s | 4m36s |
| [40094542442](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094542442) | `b138e7f2cacc` | 2026-10-24 12:35Z | push | `ubuntu-latest` | OK | 0s | 4m10s | 4m23s |
| [40094138452](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094138452) | `000fcf913d87` | 2026-10-24 12:29Z | push | `ubuntu-latest` | échec | 0s | 4m57s | 5m10s |
| [40094136595](https://github.com/Silicium-Project/FrontEnd/actions/runs/40094136595) | `000fcf913d87` | 2026-10-24 12:29Z | push | `ubuntu-latest` | échec | 0s | 4m24s | 4m35s |
| [40093938723](https://github.com/Silicium-Project/FrontEnd/actions/runs/40093938723) | `155bfd75696c` | 2026-10-24 12:26Z | push | `ubuntu-latest` | OK | 0s | 3m45s | 3m57s |
| [40093855122](https://github.com/Silicium-Project/FrontEnd/actions/runs/40093855122) | `155bfd75696c` | 2026-10-24 12:25Z | push | `ubuntu-latest` | OK | 0s | 5m01s | 5m13s |
| [40091128073](https://github.com/Silicium-Project/FrontEnd/actions/runs/40091128073) | `8bf551075df4` | 2026-10-24 11:44Z | push | `ubuntu-latest` | OK | 0s | 4m37s | 4m49s |
| [40084334196](https://github.com/Silicium-Project/FrontEnd/actions/runs/40084334196) | `f78b7e233f0d` | 2026-10-24 10:02Z | push | `ubuntu-latest` | échec | 0s | 4m53s | 5m06s |
| [40083869211](https://github.com/Silicium-Project/FrontEnd/actions/runs/40083869211) | `f78b7e233f0d` | 2026-10-24 09:55Z | push | `ubuntu-latest` | OK | 0s | 5m19s | 5m34s |
| [40083594986](https://github.com/Silicium-Project/FrontEnd/actions/runs/40083594986) | `cae4e209ca18` | 2026-10-24 09:51Z | push | `ubuntu-latest` | OK | 0s | 4m03s | 4m15s |
| [40082774896](https://github.com/Silicium-Project/FrontEnd/actions/runs/40082774896) | `30f85c54e029` | 2026-10-24 09:38Z | push | `ubuntu-latest` | échec | 0s | 8m04s | 8m19s |
| [40082299462](https://github.com/Silicium-Project/FrontEnd/actions/runs/40082299462) | `ba853f258931` | 2026-10-24 09:31Z | push | `ubuntu-latest` | échec | 0s | 1m20s | 1m31s |
| [40081892350](https://github.com/Silicium-Project/FrontEnd/actions/runs/40081892350) | `750bd01f53d7` | 2026-10-24 09:25Z | push | `ubuntu-latest` | échec | 0s | 1m31s | 1m42s |

### DesktopApp — CI (1 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40283448257](https://github.com/Silicium-Project/DesktopApp/actions/runs/40283448257) | `ef12c73350bc` | 2026-10-26 07:03Z | pull_request | `—` | ignoré | 0s | 0s | 1s |

### Network — Network CI (18 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40137778682](https://github.com/Silicium-Project/Network/actions/runs/40137778682) | `d2ffdcef04d4` | 2026-10-24 22:15Z | pull_request | `self-hosted` | annulé | 0s | 3m34s | 1m37s |
| [40086109149](https://github.com/Silicium-Project/Network/actions/runs/40086109149) | `e2eb8f109d91` | 2026-10-24 10:29Z | push | `ubuntu-latest` | échec | 0s | 39m03s | 38m51s |
| [40085504064](https://github.com/Silicium-Project/Network/actions/runs/40085504064) | `e2eb8f109d91` | 2026-10-24 10:20Z | push | `ubuntu-latest` | OK | 0s | 8m11s | 8m23s |
| [40083714983](https://github.com/Silicium-Project/Network/actions/runs/40083714983) | `f364c9e3be48` | 2026-10-24 09:53Z | push | `ubuntu-latest` | échec | 0s | 18m56s | 19m43s |
| [40083274752](https://github.com/Silicium-Project/Network/actions/runs/40083274752) | `2f2826bed4e7` | 2026-10-24 09:46Z | push | `ubuntu-latest` | annulé | 0s | 7m10s | 7m21s |
| [40080804120](https://github.com/Silicium-Project/Network/actions/runs/40080804120) | `d845688dc72f` | 2026-10-24 09:08Z | push | `ubuntu-latest` | échec | 0s | 34m05s | 33m59s |
| [39859547458](https://github.com/Silicium-Project/Network/actions/runs/39859547458) | `6f8da5509252` | 2026-10-22 21:43Z | push | `self-hosted` | annulé | 0s | 16m06s | 18m09s |
| [39857483928](https://github.com/Silicium-Project/Network/actions/runs/39857483928) | `68e0615e7a6f` | 2026-10-22 21:28Z | push | `self-hosted` | annulé | 0s | 17m09s | 17m20s |
| [39854164892](https://github.com/Silicium-Project/Network/actions/runs/39854164892) | `5f3f604cd90f` | 2026-10-22 21:03Z | push | `self-hosted` | échec | 0s | 19m07s | 19m19s |
| [39840270863](https://github.com/Silicium-Project/Network/actions/runs/39840270863) | `05d148c4e609` | 2026-10-22 19:27Z | push | `self-hosted` | échec | 0s | 1h20m52s | 1h19m08s |
| [39789219448](https://github.com/Silicium-Project/Network/actions/runs/39789219448) | `7d94cf68a07e` | 2026-10-22 13:42Z | push | `self-hosted` | échec | 2h01m00s | 1h39m23s | 2h06m47s |
| [39770909656](https://github.com/Silicium-Project/Network/actions/runs/39770909656) | `f73efa66c90a` | 2026-10-22 11:29Z | push | `self-hosted` | échec | 0s | 1h24m01s | 51m15s |
| [39730723790](https://github.com/Silicium-Project/Network/actions/runs/39730723790) | `023c038d5156` | 2026-10-22 05:54Z | push | `self-hosted` | annulé | 0s | 12m55s | 5m46s |
| [39730186339](https://github.com/Silicium-Project/Network/actions/runs/39730186339) | `c0143f906499` | 2026-10-22 05:49Z | push | `self-hosted` | annulé | 0s | 18m21s | 6m41s |
| [39721338746](https://github.com/Silicium-Project/Network/actions/runs/39721338746) | `fd540611322a` | 2026-10-22 04:15Z | push | `self-hosted` | échec | 0s | 35m29s | 30m40s |
| [39719577042](https://github.com/Silicium-Project/Network/actions/runs/39719577042) | `6ce340996d2f` | 2026-10-22 03:56Z | push | `self-hosted` | OK | 0s | 13m39s | 7m51s |
| [39696747154](https://github.com/Silicium-Project/Network/actions/runs/39696747154) | `c379ef907793` | 2026-10-21 23:57Z | push | `self-hosted` | OK | 19m42s | 30m56s | 28m29s |
| [39693051822](https://github.com/Silicium-Project/Network/actions/runs/39693051822) | `80644ba93b88` | 2026-10-21 23:23Z | push | `self-hosted` | annulé | 21m44s | 22m39s | 35m31s |

### Solana — CI (1 run(s))

| Run | Commit | Date UTC | Événement | Runner observé | Résultat | Queue | Jobs Σ | Écoulé |
|---|---|---|---|---|---|---:|---:|---:|
| [40283450884](https://github.com/Silicium-Project/Solana/actions/runs/40283450884) | `ef8f07d4fbed` | 2026-10-26 07:03Z | pull_request | `—` | ignoré | 0s | 0s | 1s |

### Integration — Full private integration (0 run(s))

Aucun run disponible à cette date.

## Contrôle du routage et décisions de migration

Le planificateur commun a été exécuté en lecture sur deux chemins d’exemple :

- `docs/operations/ci-inventory-2026-10-26.md` : chemin documentaire, `full=false`; pour Workbench public, les suites sont `docs`, `powershell`, `security`, `tooling`. Les 11 suites applicatives sont explicitement reportées à Integration.
- `contracts/job-v1.json` : contrat partagé, `full=true`; le routage conservateur marque tous les composants affectés. Le scope public exécute les quatre suites publiques et diffère les 11 suites applicatives ; Integration demande les 15 suites enregistrées. Le fichier inconnu déclenche également le routage conservateur complet.

Ces exemples valident le comportement du planificateur local, pas le déclenchement réel des workflows privés. Aucun job privé n’a été lancé.

### Ordre de travail recommandé

1. Pour [CI-01 / issue #190](https://github.com/Silicium-Project/Workbench/issues/190), garder `ci/required` comme gate public et finir l’intégration des wrappers GitHub-only. Les anciens chemins self-hosted sont désactivés ; les cinq PR natives restent brouillonnes et leurs flags à zéro.
2. Pour [CI-02 / issue #217](https://github.com/Silicium-Project/Workbench/issues/217), utiliser les exécutions répétées de mêmes SHA et les queues élevées comme cas mesurés pour les filtres de chemins, la concurrence, les caches séparés et la validation finale. Aucun contrôle requis ne doit disparaître.
3. Revoir les PR brouillon BackEnd #39, FrontEnd #28, DesktopApp #1, Network #355 et Solana #1. Vérifier que leurs wrappers appellent la bonne version du planificateur et n’ajoutent ni runner VPS ni checkout privé dans Workbench.
4. Après renouvellement du quota inclus, mesurer un run pilote privé sur un seul composant avec `SILICIUM_COMPONENT_CI_ENABLED=1`, puis vérifier le coût et les rapports avant de généraliser. Tant que le quota est épuisé, laisser les cinq flags à zéro.
5. Installer et qualifier Integration seulement après validation du pilote ; `SILICIUM_INTEGRATION_ENABLED` reste absent, donc aucun run inter-dépôts ne démarre.
6. Ne réactiver signature, publication de paquets ou déploiement dev qu’après une qualification privée réussie, vérification des signatures et parcours d’installation. La production garde son approbation humaine.
7. Vérifier séparément si les runners auto-hébergés sont encore enregistrés sur l’organisation ; l’API de runners n’était pas accessible avec les droits actuels. Les jobs sont bloqués par désactivation, mais le désenregistrement n’est pas démontré.

## Validation de cette tranche

- SHA de `main` et statut des workflows comparés aux réponses GitHub enregistrées dans le JSON joint.
- Derniers runs interrogés sans relance, avec événements, statuts, labels réels des runners et durées.
- Deux exemples de routage produits par `tools/lib/planner.mjs`.
- Aucun build, test applicatif, benchmark, changement de secret, changement de protection ou déploiement exécuté.
- Le rapport ne ferme pas l’issue : revue humaine, fusion et validation explicite des critères restent nécessaires.

## Suivi complémentaire Workbench — 26 octobre 2026

La capture multi-dépôts ci-dessus reste datée de 19:09 CEST. Pour ne pas
présenter les états privés comme rafraîchis, ce relevé ne couvre que les
20 derniers runs publics Workbench observés à 21:08 UTC ; les données JSON
complètes sont dans
[`ci-workbench-metrics-follow-up-2026-10-26.json`](ci-workbench-metrics-follow-up-2026-10-26.json).

| Mesure Workbench | Échantillon | Médiane | p95 |
|---|---:|---:|---:|
| Workflow complet, succès et échecs | 20 | 117,5 s | 354 s |
| Attente avant démarrage du workflow | 20 | 0 s | 96 s |
| Retour des voies rapides | 17 | 100 s | 31 986 s |
| Attente / provisionnement des jobs | 127 jobs | 4 s | 6 s |
| Exécution des jobs | 128 jobs | 18,5 s | 66 s |

La capture compte 16 succès, 4 échecs et aucune annulation. Le p95 du workflow
complet est de 5 min 54 s car, avec 20 observations et la règle nearest-rank,
il retient l'avant-dernière durée. Le p95 du retour rapide est dominé par un
unique run qui a attendu avant même la création de ses jobs.

Le run [40284157049](https://github.com/Silicium-Project/Workbench/actions/runs/40284157049)
a été créé à 07:10:24Z et démarré à 16:01:55Z, soit 8 h 51 min 31 s d'attente
au niveau du workflow. Il s'est terminé à 16:03:40Z après environ 1 min 45 s
d'exécution. Les jobs `quick (docs)` et `quick (tooling)` ont échoué ; le gate
a correctement échoué avec eux. L'API ne donne pas la cause de l'attente :
ne l'attribuer ni au quota ni à une saturation des runners sans preuve.

Le relevé paginé contient 101 artefacts Workbench non expirés, pour 542 090
octets (0,52 Mio), sur deux pages ; le total est complet. Ce chiffre ne couvre
pas les dépôts privés ni les caches Actions de l'organisation. Les rapports
disponibles mesurent 7 hits et 10 misses de cache sur 17 observations (41,2 %) ;
3 runs n'ont pas de rapport de cache. Cet échantillon est trop réduit pour
justifier seul une modification de stratégie de cache.
