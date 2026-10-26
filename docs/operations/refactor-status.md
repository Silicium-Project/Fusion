# Refonte : état de référence et conditions d'activation

La [PR centrale #317](https://github.com/Silicium-Project/Fusion/pull/317) a été
intégrée le 25 octobre 2026, après réussite de la qualification de sa révision
`24c7590c`. Son squash a conservé le code qualifié, mais pas l'ascendance des
imports. Le [rattachement des historiques](git-history-recovery.md) a ensuite
été intégré par la [PR #319](https://github.com/Silicium-Project/Workbench/pull/319)
avec un merge commit. Le commit de rattachement `ed5983d8` et la tête qualifiée
`873ed2f2` sont ancêtres de `main` au SHA observé
`90bec77675ca7a67c7202126386ef5dd9033b761`. Le [run `push main`
40359090517](https://github.com/Silicium-Project/Workbench/actions/runs/40359090517)
est réussi sur ce SHA exact et son contrôle `ci/required` a réussi. Le job privé
`validate` a été ignoré car ce run utilisait le scope public. L'intégration des
historiques et cette qualification `push main` sont vérifiées pour ce SHA ;
elles ne qualifient ni les composants privés ni une livraison. Ni cette page ni
une qualification CI ne valent acceptation ou déploiement.

## Décisions conservées

- Workbench (anciennement Fusion) est **public** depuis le 25 octobre 2026 à
  18:30 UTC, après validation
  du rapport, des historiques, des échanges et des ressources fournies par le propriétaire.
- Le Project 12, `planning-private` et les trois anciens dépôts restent privés.
- Aucune dépense Actions supplémentaire ; arrêt des dépassements à zéro.
- Les six anciennes inscriptions de runners VPS sont retirées. Aucun build,
  test ou packaging ne revient sur le VPS.
- Le checkout initial et ses changements restent conservés. Les travaux sont
  préparés dans une copie isolée, avec sauvegardes et carte de provenance.
- Aucun programme, wallet ou autorité Solana n'est remplacé par cette refonte.
- Le propriétaire a adopté le mode mainteneur unique le 25 octobre 2026 : PR,
  CI stricte et discussions résolues obligatoires ; revue externe facultative.
  Les approbations de production et l'acceptation humaine des issues sont conservées.

## Lots et preuves attendues

| Lot | Livrable préparé | Condition restant à démontrer ou décider |
|---|---|---|
| L0 | Références Git et GitHub, sauvegardes des historiques, patchs et fichiers locaux, inventaire des CI et runners | Conserver l'inventaire privé comme référence de restauration ; actualiser les nouvelles preuves |
| L1 | Audit d'exposition actualisé, ouverture et publication des visuels validées, HOLD isolés, contribution et consignes IA | Conserver les rapports privés et contrôler les nouveaux contenus |
| L2 | Ascendance historique réparée par #319 et qualification `push main` prouvée pour `90bec…` ; retour à des dépôts composants indépendants décidé et documenté dans l'ADR | Réaliser la séparation des composants privés, fixer les pins/gitlinks et réconcilier les PR de migration monorepo avec cette décision ; qualifier l'intégration privée avant livraison |
| L3 | Workbench public, runners CI VPS retirés, règles de contribution et mode mainteneur unique définis | Confirmer les règles d'accès/environnements sur les composants privés et ne pas confondre le gate public avec leur qualification |
| L4 | `dev`/`dev.ps1`, registre, routage, contrôle final, normes, diagnostics et métriques | Résultat GitHub complet du commit évalué et parcours Windows/Anchor ; voir les checks de la PR |
| L5 | Construction sur GitHub, manifeste, signatures et snapshots, tests d'installation, application et rollback API/web | Provisionner les signatures/SSH, qualifier installations et mises à niveau, adopter le VPS et démontrer le rollback ; drainage/canari runtime toujours bloquants |
| L6 | Champs du Project, App installée et accès protégés provisionnés, réconciliation qualifiée en lecture, acceptation avec preuves et procédures IA | Intégrer le workflow revu, qualifier son exécution GitHub puis activer la synchronisation et retirer les automatismes natifs remplacés |

Les imports mécaniques, la mise à niveau Go et l'alignement SDK disposent de
PR de revue séparées (#314, #315, #316). La normalisation initiale est isolée
dans #318. Conserver les merges d'historiques : ne pas squash/rebase l'import.

## Observations vérifiées à ce point de référence

La [qualification 40197099773](https://github.com/Silicium-Project/Fusion/actions/runs/40197099773)
a passé 12 suites sur 14 : API, web, desktop UI/Linux, runtime Rust, WASM,
intégration P2P, infrastructure, PowerShell, sécurité, documentation et outillage.
Elle a révélé un lint Windows et l'absence du verrou Rust Solana. Ces défauts
ont été corrigés ensuite ; leur correction exige une nouvelle qualification,
elle ne transforme pas l'ancien run en succès.

La tentative suivante,
[40199389136](https://github.com/Silicium-Project/Fusion/actions/runs/40199389136),
a été refusée par GitHub avant l'allocation de runners, pour un motif de
facturation ou de limite de dépenses. Aucun test de cette tentative n'a
démarré. L'écran de facturation fourni ensuite par le propriétaire confirme
**2 000 minutes utilisées sur 2 000 incluses** pour l'organisation. Cette
tentative privée précède l'ouverture ; le plafond reste à zéro.

La [qualification publique 40223122663](https://github.com/Silicium-Project/Fusion/actions/runs/40223122663)
a ensuite réussi les **14 suites**, dont Windows et Solana, pour la tête de PR
`03e62285bb7c3cc95f1c375416667f148a505cc3` : 975 tests/scénarios observés, contrôle
`ci/required` réussi et rapports vérifiés. Les changements ultérieurs doivent
obtenir leur propre qualification ; ces résultats ne valent pas déploiement.

La [qualification 40232356923](https://github.com/Silicium-Project/Fusion/actions/runs/40232356923)
a réussi les 14 suites et `ci/required` sur `24c7590c`, avant la fusion de #317.
Le job Solana a pris 13 min 13 s et l'outillage a exécuté 93 tests. Après le
rattachement #319, le [run `push main` 40359090517](https://github.com/Silicium-Project/Workbench/actions/runs/40359090517)
a réussi sur le SHA exact `90bec77675ca7a67c7202126386ef5dd9033b761` ;
`ci/required` est réussi et `validate` est ignoré car le scope est public. Le
blocage d'ascendance et de qualification `push` décrit dans le rapport initial
est levé pour ce SHA. Les validations privées et la livraison restent distinctes.

Le run a exécuté notamment 151 tests Go, 112 unités web et 56 scénarios
navigateur, 34 unités natives Linux, 323 tests runtime et 69 tests WASM. Les
trois scénarios P2P existants et 22 tests Python réseau ont passé. Ces scénarios
ne prouvent pas toutes les fonctionnalités futures de délégation organique.

Le moteur Project a été exécuté **sans écriture** sur les 134 issues actives :
32 éléments du dépôt privé d'arbitrage sont restés exclus. Les transitions
proposées et blocages restent un diagnostic, sans acceptation ni clôture.

L'App dédiée a ensuite été créée et installée sur les huit dépôts de
l'organisation ; ses secrets sont dans `project-automation`. Le jeton limité
à Fusion/planning-private, avec uniquement des droits en lecture pour cette
qualification, observe les mêmes 134 issues sans écriture. Un second jeton,
limité à Actions/metadata en lecture, vérifie le stockage des huit dépôts et
la réserve d'artefacts. Le JWT de vérification de l'installation utilise le
schéma HTTP Bearer attendu par GitHub ; aucune clé ni aucun jeton n'est publié.

Les résultats d'installation APT/DNF/NSIS, de canari et de rollback ne sont
pas encore fournis par une livraison réelle. Un rendu Compose ou des tests
unitaires de scripts ne remplacent pas ces preuves.

## Activation restante, dans l'ordre

1. Réconcilier les PR de migration encore ouvertes avec la décision multi-dépôts :
   les sources applicatives doivent rester dans leurs dépôts privés ; Workbench
   porte la composition, la politique commune et les procédures. Rattacher les
   composants par leurs pins Git documentés et conserver les références d'origine.
2. Garder les qualifications privées suspendues tant que quota et budget strict
   à zéro ne permettent pas une preuve sans dépassement. Les jobs différés restent
   bloquants pour toute livraison.
3. Conserver les livraisons désactivées pendant la qualification publique et
   la préparation des signatures et accès. L'ouverture du code n'est pas une
   qualification du candidat ni une acceptation de livraison.
4. Après intégration et revue du workflow, qualifier la réconciliation GitHub
   avec l'App déjà installée avant toute synchronisation active. Conserver les
   anciens automatismes jusqu'à validation de leur remplacement.
5. Rétablir la clé d'auto-update correspondant à celle des clients, ou qualifier
   une migration de confiance revue. La dérive constatée reste bloquante.
6. Provisionner les environnements de signature et déploiement par un canal
   sécurisé ; qualifier les paquets et leur mise à niveau sur GitHub.
7. Adopter les artefacts actuellement servis comme référence de rollback,
   préserver volumes et identités et retirer le publisher historique.
8. Qualifier drainage, canari et reprise avant tout changement d'image réseau.
   Une télémétrie absente ou un simple healthcheck n'autorisent pas un arrêt.
9. Démontrer dev, promotion prod et rollback, puis demander les acceptations
   humaines des issues de gouvernance/CI/QRE concernées.

Voir [l'activation détaillée](bootstrap.md), [la livraison](delivery.md),
[la revue d'exposition](exposure-review.md) et [les parcours IA](../ai/README.md).
