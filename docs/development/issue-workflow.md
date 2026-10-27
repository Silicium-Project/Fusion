# Issues, préparation, revue et acceptation

## Références et provenance

Ce workflow reprend les propositions Fusion #242, Network #354, BackEnd #38 et
FrontEnd #27. Leurs formulaires communs sont regroupés à la racine de Workbench.
Les changements utiles sont reportés ; les PR d'origine restent ouvertes tant
que l'intégration n'a pas été acceptée.

Le Project 12 et le dépôt `planning-private` restent privés. Les issues actives
de Workbench et ses milestones forment la roadmap publiable. Une décision HOLD
n'est ni un abandon, ni un élément à exposer dans un rapport public.

## Préparer une tranche

1. Choisir une issue ouverte ; vérifier son parent et ses dépendances natives.
2. Donner un responsable, une taille, un résultat borné, des critères d'acceptation
   sous forme de checklist et une cible : Documentation, CI, Dev ou Prod.
3. Définir `Préparation = Validée` après revue du périmètre et des tests attendus.
4. L'issue devient `Prêt` lorsque ses dépendances sont acceptées.
5. `./dev issue start URL` vérifie les champs, dépendances et WIP ; `--apply`
   applique le passage à `En cours`. Une seule tranche active par personne.

Le chantier de migration est une tranche transversale explicitement demandée,
découpée en commits et PR de revue. Ses lots ne clôturent pas les issues de
gouvernance, QRE ou CI avant leurs propres preuves d'acceptation.

## Relier les PR

Utiliser `Refs: https://github.com/Silicium-Project/Workbench/issues/NUMERO` dans
chaque PR. Plusieurs PR peuvent contribuer à une même issue. Les mots-clés de
clôture automatique ne font pas partie de ce workflow.

Écrire une ligne `Refs:` par URL, sans fragment ni paramètres. Une simple
mention dans un paragraphe est informative et ne rend pas la PR obligatoire
pour l'acceptation. Les liens sont comparés exactement : l'issue 21 n'hérite
pas des PR de l'issue 210. Une contribution remplacée doit être arbitrée
explicitement dans les PR et leurs références ; une fermeture sans fusion
n'est jamais déduite comme une réalisation.

Une PR brouillon indique du travail commencé. `Revue` exige que toutes les PR
actives soient prêtes et que leur contrôle `ci/required` soit réussi pour leur
dernier commit. Une PR fermée sans fusion ne vaut pas livraison.

`main` utilise le mode mainteneur unique décidé par le propriétaire le
25 octobre 2026 : PR obligatoire, contrôle CI obligatoire lié à GitHub Actions,
branche à jour et discussions résolues. Aucune approbation par un autre compte
n'est imposée ; CODEOWNERS conserve la carte des responsabilités. Le mainteneur
examine les changements et décide de la fusion, même s'il en est l'auteur.
La revue automatisée reste une aide. Les protections de production et la
décision humaine d'acceptation des issues ne sont pas supprimées.

Après fusion, l'issue reste en `Validation`. Ni un ancien événement CI, ni une
fusion ne suffisent à la déclarer terminée. La réconciliation consulte les
preuves actuelles ; les événements répétés ne créent pas de doublon. Le champ
`Blocage` conserve les motifs saisis par un mainteneur et les distingue des
résumés de synchronisation marqués `[auto]`. La réconciliation recalcule et
remplace uniquement ses propres résumés ; elle n'efface jamais un motif manuel
tel qu'un quota épuisé ou un accès externe manquant. Les résumés automatiques
pointent vers les dépendances, sous-tâches, contrôles, revues ou preuves
manquantes. Les trois messages simples produits par l'ancien synchroniseur sont
retirés lors de la migration. Le préfixe `[auto]` est réservé aux messages
générés. Une issue fermée sans preuve d'acceptation vérifiée reste en
`Validation`, même si GitHub la marque comme terminée.

## Accepter

```sh
./dev issue accept ISSUE_URL --evidence https://github.com/Silicium-Project/Workbench/actions/runs/ID --human-approved
```

Le premier appel décrit l'opération. `--apply` enregistre la preuve, applique
`Terminé` et clôture l'issue. L'approbation humaine doit avoir réellement été
donnée ; un agent ne doit pas s'attribuer cette approbation par la seule présence
du drapeau. Les droits GitHub du contributeur restent vérifiés.

La commande vérifie la checklist, les enfants obligatoires, toutes les PR liées,
leur fusion par un humain autorisé en écriture et l'inclusion des changements
dans la preuve. L'auteur peut être cet humain ; aucun bot ne peut s'y substituer.
La preuve conserve le mode de contribution, les SHA et l'identité de fusion.
Une cible Dev/Prod exige aussi une livraison réussie du candidat exact. Une
phase dont un livrable obligatoire reste ouvert ne peut pas être acceptée.

Une dépendance fermée exige aussi `Status = Terminé` dans le Project ; une
fermeture manuelle sans acceptation ne suffit pas. Une dépendance absente de
l'inventaire ou une liste de relations tronquée bloque la transition : il
faut restaurer les données ou étendre la pagination, jamais ignorer le reste.

L'abandon ou le doublon est une décision explicite (`Abandonné`). Les issues
HOLD exigent un arbitrage individuel dans l'espace privé.

## Activation de l'automatisation

Le workflow `Project sync` est actif depuis le 27 octobre 2026 avec
`SILICIUM_PROJECT_AUTOMATION_ENABLED=1`. Son premier apply GitHub
([40469270941](https://github.com/Silicium-Project/Workbench/actions/runs/40469270941))
a traité les 139 issues Workbench et écrit 9 changements de statut et 139
résumés de blocage. Il exclut les éléments du dépôt privé `planning-private`
et les cartes sans issue. Le Project 12 reste privé.

Le déclenchement manuel `workflow_dispatch` utilise `mode=dry-run` par défaut,
uniquement depuis `main`. Il utilise un jeton App avec les droits du Project en
lecture seule et n'affiche que le nombre d'items et les changements prévus, sans
URL d'issue, PR privée ni texte de blocage. Les lectures des PR et des checks
Workbench, Integration et des cinq composants utilisent des jetons distincts,
éphémères et limités à `pull_requests:read` et `checks:read` pour les dépôts
privés. Le workflow ne clone et n'exécute jamais le code d'une PR privée. Les
événements GitHub reçus par Workbench et le rapprochement toutes les quinze
minutes couvrent aussi les dépôts privés, qui ne déclenchent pas le workflow
public directement. Ce mode reste disponible même si le flag vaut `0`. Le mode
`apply`, les événements d'issue/PR/CI et le rapprochement périodique exigent le
flag à `1`.

L'automatisation modifie seulement les champs `Status` et `Blocage` du Project.
Elle ne crée, ne ferme, n'assigne et ne commente aucune issue. Elle ignore les
issues `HOLD` ou `Arbitrage`. La règle de statut est :

- issue en attente de qualification ou de préparation : `À qualifier` ou
  `Backlog` ; une issue préparée, assignée et sans dépendance ouverte peut
  passer à `Prêt` ;
- PR liée brouillon, CI en attente/échec ou demande de changement : `En cours` ;
- toutes les PR liées actives de Workbench, des composants et d'Integration
  prêtes, avec leur gate requis réussi et sans demande de changement : `Revue` ;
- une PR privée sans gate `ci/required` unique ou avec contrôle en attente reste
  en `En cours` avec un blocage automatique ; elle ne vaut pas une qualification ;
- fusion d'une PR ou fermeture manuelle comme terminée sans preuve complète :
  `Validation` ;
- `Terminé` exige l'acceptation humaine, une preuve de la cible et les
  dépendances, sous-tâches et PR acceptées ; l'automatisation ne clôt pas l'issue ;
- abandon explicitement indiqué dans GitHub : `Abandonné`.

Le champ `Blocage` conserve les motifs manuels. Les motifs générés sont marqués
`[auto]`, remplacés à chaque réconciliation, et décrivent les dépendances, les
contrôles, la revue ou les preuves manquantes. Les journaux publics Workbench
n'exposent que des compteurs agrégés. Le dry-run de vérification
[40471477621](https://github.com/Silicium-Project/Workbench/actions/runs/40471477621)
a traité les 139 issues avec zéro changement prévu après l'événement CI de #325.
Voir [l'activation](../operations/bootstrap.md).

Les lectures REST et les requêtes GraphQL réessaient au plus deux fois après
une erreur réseau transitoire identifiée, avec une attente bornée. Les mutations
ne sont jamais rejouées automatiquement ; les réponses de limitation GitHub
restent visibles et attendent une exécution ultérieure.
