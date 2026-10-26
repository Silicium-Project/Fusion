# Rattacher les historiques après le squash de #317

## État observé

Le propriétaire a intégré [#317](https://github.com/Silicium-Project/Fusion/pull/317)
le 25 octobre 2026 à 21:05:08 UTC. GitHub a employé un squash : le commit
`e0183e8bf5144c88c779830f058bad9393267ac6` ne possède qu'un parent,
`6b7673e33d700a31134e231792ed7e97ce41d3b3`.

La révision qualifiée était `24c7590c02eeeebcb0fb1ef8c0aa01aa576fd039`.
Les deux révisions ont exactement le même arbre Git :
`8f105674a392c400178e507cb6ec38741f2f62a3`. Le code intégré correspond donc au
code testé ; le problème concerne l'ascendance des imports. **1 252 commits**
accessibles depuis cette révision n'étaient pas des ancêtres de `main`.

La branche source et les anciens dépôts conservent les historiques. Une nouvelle
sauvegarde Git complète des deux références a été créée hors du dépôt, dans
l'espace privé, et vérifiée avec `git bundle verify` avant la réparation.

Le message du squash agrège aussi une ancienne directive de désactivation CI.
GitHub peut ainsi ignorer les événements `push` et `pull_request`, comme décrit
dans [sa documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).
Aucune exécution CI `push` n'a été créée pour `e0183e8b` lors du constat.
Les indicateurs de livraison, de synchronisation Project et de diagnostic
restent à zéro ; cette fusion n'a déclenché aucun déploiement.

## Réparation intégrée

La branche `lf-fix-210-restore-import-history` part de `e0183e8b` et contient
une fusion normale de `24c7590c`, sans squash ni rebase. Son commit de
rattachement est `ed5983d827c26b66f47f20f36ac21a3e37122617` : ses deux parents
sont le squash déjà intégré et la révision qualifiée. Son arbre reste
exactement celui du squash. La [PR #319](https://github.com/Silicium-Project/Workbench/pull/319)
a intégré ce commit par merge commit `ff14db3c666eb9f355f59bfa908a48f0e7a44e6c`
le 25 octobre 2026.

Les changements suivants documentent l'incident et sa reprise. Aucun commit
existant de `main` n'est réécrit. Le merge commit a conservé l'ascendance ; un
nouveau squash de cette réparation aurait annulé son objectif.

Pour empêcher cette répétition, les options squash et rebase du dépôt ont été
désactivées. Au 26 octobre 2026, l'API GitHub confirme `allow_merge_commit=true`,
`allow_squash_merge=false` et `allow_rebase_merge=false`. La fusion normale
reste disponible. Les autres protections de branche et les protections de
production sont conservées. Leurs réglages précédents sont sauvegardés dans le
même espace privé.

## Vérification initiale

Depuis un checkout à jour de la branche de réparation :

```sh
git merge-base --is-ancestor e0183e8bf5144c88c779830f058bad9393267ac6 HEAD
git merge-base --is-ancestor 24c7590c02eeeebcb0fb1ef8c0aa01aa576fd039 HEAD
git diff --exit-code e0183e8bf5144c88c779830f058bad9393267ac6 ed5983d8
git show --no-patch --format='%H%n%P%n%T' ed5983d8
./dev ci plan --base origin/main --head HEAD --json
```

Les trois premières commandes doivent réussir. Les quatre imports (Fusion,
Network, BackEnd et FrontEnd) et leurs merges deviennent ainsi des ancêtres
de la branche. La PR doit conserver tous ces commits et passer `ci/required`.
Le plan de cette correction documentaire exige les quatre suites `docs`,
`powershell`, `security` et `tooling`. Le code applicatif a le même arbre que
la révision qualifiée ; ces quatre suites ne sont pas une nouvelle
qualification complète des applications.

## Qualification après intégration

Le contrôle a été exécuté sur `origin/main` au SHA
`90bec77675ca7a67c7202126386ef5dd9033b761` :

```sh
git merge-base --is-ancestor ed5983d827c26b66f47f20f36ac21a3e37122617 origin/main
git merge-base --is-ancestor 873ed2f2156abddb6d633e42ce615eed967d43a2 origin/main
gh run view 40359090517 --repo Silicium-Project/Workbench
```

Les deux tests d'ascendance réussissent. Le run
[40359090517](https://github.com/Silicium-Project/Workbench/actions/runs/40359090517)
est un événement `push` sur `main`, sur le SHA exact ci-dessus, avec conclusion
`success` pour le run et `ci/required`. Le job `validate` est `skipped` : ce
workflow qualifie le scope public et ne récupère pas les sources privées.
Cette preuve lève le blocage d'ascendance et de `push main` pour ce SHA ; elle
ne vaut pas qualification privée des applications, acceptation des issues ou
autorisation de livraison.

Pour toute nouvelle révision de `main`, réactualiser les références et répéter
les tests d'ascendance et la vérification du run `push` sur le SHA précis. Une
absence de run ne vaut jamais une réussite.

## Procédure historique de fusion

La fusion humaine a été réalisée avec **Merge commit** :

1. Conserver les livraisons désactivées jusqu'aux qualifications et accès décrits
   dans [le bootstrap](bootstrap.md). Les données du VPS restent en place.
2. Réexaminer les modes de fusion après la fin de la migration des historiques ;
   ne pas réactiver automatiquement squash ou rebase.

Cette procédure ne vaut ni acceptation des issues de migration, ni validation
du drainage des workers, des signatures ou des installations APT/DNF/Windows.
