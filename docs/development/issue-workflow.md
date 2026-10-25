# Issues, préparation, revue et acceptation

## Références et provenance

Ce workflow reprend les propositions Fusion #242, Network #354, BackEnd #38 et
FrontEnd #27. Leurs formulaires communs sont regroupés à la racine du monorepo.
Les changements utiles sont reportés ; les PR d'origine restent ouvertes tant
que l'intégration n'a pas été acceptée.

Le Project 12 et le dépôt `planning-private` restent privés. Les issues actives
de Fusion et ses milestones forment la roadmap publiable. Une décision HOLD
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

Utiliser `Refs: https://github.com/Silicium-Project/Fusion/issues/NUMERO` dans
chaque PR. Plusieurs PR peuvent contribuer à une même issue. Les mots-clés de
clôture automatique ne font pas partie de ce workflow.

Une PR brouillon indique du travail commencé. `Revue` exige que toutes les PR
actives soient prêtes et que leur contrôle `ci/required` soit réussi pour leur
dernier commit. Une PR fermée sans fusion ne vaut pas livraison.

Après fusion, l'issue reste en `Validation`. Ni un ancien événement CI, ni une
fusion ne suffisent à la déclarer terminée. La réconciliation consulte les
preuves actuelles ; les événements répétés ne créent pas de doublon.

## Accepter

```sh
./dev issue accept ISSUE_URL --evidence https://github.com/Silicium-Project/Fusion/actions/runs/ID --human-approved
```

Le premier appel décrit l'opération. `--apply` enregistre la preuve, applique
`Terminé` et clôture l'issue. L'approbation humaine doit avoir réellement été
donnée ; un agent ne doit pas s'attribuer cette approbation par la seule présence
du drapeau. Les droits GitHub du contributeur restent vérifiés.

La commande vérifie la checklist, les enfants obligatoires, toutes les PR liées,
leur revue humaine indépendante et l'inclusion des changements dans la preuve.
Une cible Dev/Prod exige aussi une livraison réussie du candidat exact. Une
phase dont un livrable obligatoire reste ouvert ne peut pas être acceptée.

L'abandon ou le doublon est une décision explicite (`Abandonné`). Les issues
HOLD exigent un arbitrage individuel dans l'espace privé.

## Activation de l'automatisation

Les champs sont créés. Le moteur et le workflow de réconciliation sont fournis.
Leur exécution reste désactivée avant la création/installation de l'App dédiée
et la qualification de ses droits. Voir [l'activation](../operations/bootstrap.md).
