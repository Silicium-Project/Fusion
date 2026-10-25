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

## Réparation préparée

La branche `lf-fix-210-restore-import-history` part de `e0183e8b` et contient
une fusion normale de `24c7590c`, sans squash ni rebase. Son commit de
rattachement est `ed5983d8` : ses deux parents sont le squash déjà intégré et
la révision qualifiée. Son arbre reste exactement celui du squash.

Les changements suivants documentent l'incident et sa reprise. Aucun commit
existant de `main` n'est réécrit. La fusion de cette branche doit conserver son
ascendance ; un nouveau squash annulerait le but de la réparation.

Pour empêcher cette répétition, les options squash et rebase du dépôt ont été
désactivées temporairement. La fusion normale reste disponible. Les autres
protections de branche et les protections de production sont conservées.
Leurs réglages précédents sont sauvegardés dans le même espace privé.

## Vérification et qualification

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
La modification d'`AGENTS.md` exige une qualification conservatrice complète.

Après décision humaine de fusion avec **Merge commit** :

1. Actualiser `origin/main` et refaire les vérifications d'ascendance sur cette
   référence. Ne supprimer aucune source de provenance avant ce contrôle.
2. Vérifier la qualification `push` du SHA exact de `main`. Les anciennes
   directives présentes dans les commits importés peuvent encore perturber le
   déclenchement ; une absence de run ne vaut jamais une réussite.
3. Si aucun run n'est créé, soumettre une petite PR suivante avec un message
   propre pour déclencher un nouveau push une fois les historiques rattachés.
   Une exécution manuelle peut servir au diagnostic ; elle ne remplace pas la
   preuve `push main` exigée pour la livraison et l'acceptation.
4. Conserver les livraisons désactivées jusqu'aux qualifications et accès décrits
   dans [le bootstrap](bootstrap.md). Les données du VPS restent en place.
5. Réexaminer les modes de fusion après la réparation et sa qualification ; ne
   pas réactiver automatiquement le squash pendant les imports d'historiques.

Cette procédure ne vaut ni acceptation des issues de migration, ni validation
du drainage des workers, des signatures ou des installations APT/DNF/Windows.
