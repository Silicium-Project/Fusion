# Refonte : état de référence et conditions d'activation

## Mise à jour opérationnelle — 28 octobre 2026 (14:29 UTC)

- Les contrôles de PR privés sont opérationnels sous la configuration Enterprise
  actuelle : Integration #4 et #5 ont `integration/required` et CodeQL verts ;
  les PR de restauration BackEnd #39, FrontEnd #28, Network #355, DesktopApp #1
  et Solana #1 ont leurs suites de qualification vertes sur leur HEAD courant.
  Cela confirme l'exécution des workflows hébergés privés, pas encore la
  qualification complète de leur composition intégrée.
- Le workflow complet reste volontairement limité à `Integration/main`, car
  Workbench ne matérialise les sources privées que depuis cette référence. Le
  run de branche [40701623830](https://github.com/Silicium-Project/Integration/actions/runs/40701623830)
  s'est arrêté avant la récupération de tout code privé. Le flag de campagne
  reste à `0` et aucun run complet n'est actif.
- Les budgets avec limite ne sont pas disponibles pendant l'essai Enterprise :
  ni l'attestation manuelle ni l'usage inclus ne constituent un coupe-circuit
  fiable à 0 $. Avant une campagne complète, vérifier le solde courant, le pire
  cas du plan, le stockage et l'absence de concurrence ; ne pas lancer si un
  de ces éléments est inconnu ou insuffisant.
- La campagne attend encore les fusions humaines des PR de restauration
  nécessaires, de Workbench #344 (routage des sources privées) et des PR
  Integration #4/#5. Après intégration, relancer d'abord les contrôles de
  `main`, puis la qualification privée bornée.

## Mise à jour opérationnelle — 28 octobre 2026 (14:16 UTC)

- `Workbench/main` est `2e563f28c1d03adb210ecc6c62043b6374c91be7`. Le run
  public [40701113568](https://github.com/Silicium-Project/Workbench/actions/runs/40701113568)
  a passé `ci/required`. Le dry-run Project
  [40703262976](https://github.com/Silicium-Project/Workbench/actions/runs/40703262976)
  a traité 139 issues et prédit zéro changement de statut ou de blocage.
- Les PR de restauration privées BackEnd #39, FrontEnd #28, Network #355,
  DesktopApp #1 et Solana #1 ont toutes leurs checks de qualification verts sur
  leur HEAD courant ; elles restent des PR de branche, certaines en brouillon.
- Le trial Enterprise affiche 30 jours restants. À 14:06 UTC, Actions affichait
  207,7/3 000 minutes utilisées, 0 $ facturé après crédits et 0/50 Go de
  stockage. Le trial exclut le budget avec arrêt à une limite : l'attestation
  Integration n'est pas un plafond de facturation. Réserver au plus 555 minutes
  Linux équivalentes pour la matrice Integration actuelle, après nouvelle
  mesure du solde juste avant le run.
- Le flag `SILICIUM_INTEGRATION_ENABLED` est `0` et aucun run Integration n'est
  en cours. Le dispatch de branche
  [40701623830](https://github.com/Silicium-Project/Integration/actions/runs/40701623830)
  a validé le plan et la preuve de stockage, puis Workbench a refusé la
  matérialisation depuis une ref autre que `Integration/main`. Aucun contenu
  privé n'a été récupéré et aucune suite applicative n'a été exécutée ; le run
  a été arrêté.
- Integration #4 (`a02bda5`) a `integration/required` et CodeQL verts et impose
  maintenant le dispatch sur `main`. Workbench #344, qui corrige le routage des
  sources de deux suites privées, reste en brouillon ; Integration #5 reste
  également ouverte. La qualification complète attend leur résolution et une
  fusion humaine des PR nécessaires.

## Mise à jour opérationnelle — 27 octobre 2026

État vérifié sur Workbench `main` au commit `cc5e7a1cfadc73ca910264aad28e5658a311069b` :

- Les PR #332, #322 et #323 sont fusionnées. Le CI du nouveau `main` a réussi ;
  les suites publiques sont qualifiées et les suites privées restent réservées
  à Integration.
- La PR #325 a été actualisée puis fusionnée dans le commit
  `96c9067371d73c4d3fb46ffdb055e877904bc753` ; ses suites publiques et
  `ci/required` ont réussi au run [40469466715](https://github.com/Silicium-Project/Workbench/actions/runs/40469466715).
  La PR #324 est en cours de réintégration sur le `main` courant.
- La synchronisation du Project est active. Le premier apply
  [40469270941](https://github.com/Silicium-Project/Workbench/actions/runs/40469270941)
  a modifié 9 statuts et 139 champs de blocage sur les 139 issues Workbench ;
  les éléments de `planning-private` restent exclus. Le dry-run de contrôle
  [40471477621](https://github.com/Silicium-Project/Workbench/actions/runs/40471477621)
  a ensuite prévu zéro changement après la qualification de #325 ; les journaux
  restent agrégés et ne révèlent pas les issues privées.
- Integration reste privé. Son dernier relevé ne montrait aucune variable
  d'activation ; la dernière capture de facturation fournie signalait les
  2 000 minutes privées incluses consommées. Aucune qualification privée n'a
  été lancée et aucun runner VPS n'est utilisé.
- `SILICIUM_DELIVERY_ENABLED=0` et `SILICIUM_DIAGNOSTICS_ENABLED=0` ; aucun
  déploiement n'a été déclenché. La PR privée Integration #4 reste à qualifier
  après vérification humaine du quota.

Les sections suivantes conservent le rapport détaillé antérieur et ses preuves
historiques ; leurs nombres et états ne décrivent pas tous le `main` courant.

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
- Objectif : aucun dépassement Actions payé. Le trial courant n'inclut pas de
  budget GitHub avec arrêt à 0 $ ; les qualifications sont manuelles et
  bornées, avec contrôle du solde juste avant le lancement. L'attestation n'est
  pas un coupe-circuit et aucun runner VPS ne sert de secours.
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
| L2 | #319 a rétabli l'ascendance ; cinq dépôts composants privés existent et Workbench les référence par gitlinks/locks ; vérification locale matérialisée réussie | Les pins actuels sont les têtes des cinq PR d'export, pas des ancêtres des `main` natifs. Qualifier et intégrer ces PR, puis repinner les commits acceptés. Déplacer aussi le runtime IA desktop encore présent comme dossier public ordinaire |
| L3 | Workbench public, runners CI VPS retirés, règles de contribution et mode mainteneur unique définis | Confirmer les protections et environnements privés ; le gate public ne qualifie pas les composants privés |
| L4 | `dev`/`dev.ps1`, registre, routage, contrôle final, normes, diagnostics et métriques | Résultat GitHub complet du commit évalué et parcours Windows/Anchor ; voir les checks de la PR |
| L5 | Construction sur GitHub, manifeste, signatures et snapshots, tests d'installation, application et rollback API/web | Provisionner les signatures/SSH, qualifier installations et mises à niveau, adopter le VPS et démontrer le rollback ; drainage/canari runtime toujours bloquants |
| L6 | Champs du Project, App installée et accès protégés provisionnés, acceptation avec preuves et procédures IA ; la réconciliation a réussi en dry-run sur 139 issues avec zéro changement prédit | Intégrer les workflows revus, qualifier l'exécution GitHub après fusion et retirer les automatismes natifs uniquement après vérification de leurs remplacements |

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
tentative privée précède l'ouverture ; à cette date, le propriétaire indiquait
que les dépassements étaient bloqués. Ce relevé ne décrit pas la capacité du
trial Enterprise ultérieur.

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

Le contrôle `dev workspace verify --materialized --json` réussit sur le checkout
de référence : les cinq gitlinks correspondent aux SHA de `components.lock.json`
et les cinq sources sont matérialisées. L'API GitHub confirme que BackEnd,
FrontEnd, DesktopApp, Network et Solana sont privés. À la date de ce relevé, les
SHA verrouillés correspondent aux têtes des PR natives d'export ; aucun n'est
encore ancêtre du `main` natif. Les PR doivent être qualifiées et intégrées avant
que les pins représentent des versions acceptées.

Le tree public observé contient aussi `apps/silicium-ai-runtime` comme dossier
ordinaire : le code Tauri du composant DesktopApp le charge par chemins relatifs.
La PR native DesktopApp a été actualisée pour intégrer ce paquet dans le dépôt
privé et corriger les chemins ; le gitlink Workbench reste à l'ancien SHA tant
qu'une PR d'intégration distincte ne l'a pas repinné et retiré du tree courant.
Le snapshot et son historique antérieur restent publics, selon la décision
explicite du propriétaire ; cette migration ne réécrit aucun commit.

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

1. Repinner DesktopApp sur le commit qui contient son runtime IA privé et retirer
   `apps/silicium-ai-runtime` du tree Workbench courant, sans purger son historique.
2. Garder les flags privés fermés hors des runs manuels bornés. Le trial ne
   fournit pas de budget avec arrêt à 0 $ : mesurer le solde juste avant le run,
   vérifier l'absence de concurrence et comparer le plan pondéré au solde. La
   qualification Integration attend aussi l'intégration des PR de composition
   et de workflow ; les jobs différés restent bloquants pour toute livraison.
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
