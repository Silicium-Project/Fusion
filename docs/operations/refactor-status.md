# Refonte : état de référence et conditions d'activation

## Mise à jour opérationnelle — 27 octobre 2026

État vérifié sur Workbench `main` au commit `a20fcf252fa8d3e26bc61f4f821a416cc61f08b7` :

- Les PR #332, #322, #323, #325 et #324 sont fusionnées. Le run `push main`
  [40472201296](https://github.com/Silicium-Project/Workbench/actions/runs/40472201296)
  a réussi sur ce SHA, y compris `ci/required`. Les contrôles publics ont passé ;
  le job applicatif `validate` est ignoré en scope public. Cela ne constitue pas
  une qualification privée des cinq composants.
- La PR #325 a été actualisée puis fusionnée dans le commit
  `96c9067371d73c4d3fb46ffdb055e877904bc753` ; ses suites publiques et
  `ci/required` ont réussi au run [40469466715](https://github.com/Silicium-Project/Workbench/actions/runs/40469466715).
  La PR #324 a été intégrée dans `a20fcf252fa8d3e26bc61f4f821a416cc61f08b7`.
- La synchronisation du Project est active. Le premier apply
  [40469270941](https://github.com/Silicium-Project/Workbench/actions/runs/40469270941)
  a modifié 9 statuts et 139 champs de blocage sur les 139 issues Workbench ;
  les éléments de `planning-private` restent exclus. Le dry-run de contrôle
  [40471477621](https://github.com/Silicium-Project/Workbench/actions/runs/40471477621)
  a ensuite prévu zéro changement après la qualification de #325 ; les journaux
  restent agrégés et ne révèlent pas les issues privées.
- Après l'ajout à la PR #326 de la ligne de référence canonique `Refs:`, le run
  [40473660391](https://github.com/Silicium-Project/Workbench/actions/runs/40473660391)
  a automatiquement déplacé GOV-02 (#210) de `Validation` à `En cours`. L'issue
  est restée ouverte ; aucun commentaire, assignation ou clôture n'a été créé.
- La PR #326 reste en brouillon. Sa branche a intégré `main` jusqu'au commit
  `a20fcf2`, retire le runtime IA du tree public courant et pointe DesktopApp,
  BackEnd et Network vers les têtes de leurs PR d'export. Cette révision doit
  rester non fusionnée : le run public
  [40472945639](https://github.com/Silicium-Project/Workbench/actions/runs/40472945639)
  a réussi sur `e0b103e`, mais `validate` a été ignoré en scope public. Ces pins
  ne sont pas des versions acceptées et les trois PR natives restent ouvertes.
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
| L2 | #319 a rétabli l'ascendance ; cinq dépôts composants privés existent et Workbench les référence par gitlinks/locks ; la PR #326 retire le runtime IA du tree public courant | Les pins restent des têtes de PR d'export et ne sont pas acceptés. Qualifier et intégrer les PR natives, puis repinner les commits acceptés ; garder #326 en brouillon jusqu'à cette décision et à sa qualification |
| L3 | Workbench public, runners CI VPS retirés, règles de contribution et mode mainteneur unique définis | Confirmer les protections et environnements privés ; le gate public ne qualifie pas les composants privés |
| L4 | `dev`/`dev.ps1`, registre, routage, contrôle final, normes, diagnostics et métriques | Résultat GitHub complet du commit évalué et parcours Windows/Anchor ; voir les checks de la PR |
| L5 | Construction sur GitHub, manifeste, signatures et snapshots, tests d'installation, application et rollback API/web | Provisionner les signatures/SSH, qualifier installations et mises à niveau, adopter le VPS et démontrer le rollback ; drainage/canari runtime toujours bloquants |
| L6 | Champs du Project, App installée et accès protégés provisionnés ; synchronisation activée et dry-run de contrôle sans changement | Continuer à contrôler les réconciliations, garder les arbitrages et acceptations humains, puis retirer les automatismes natifs seulement après vérification de leur remplacement |

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

1. Qualifier les PR natives DesktopApp #1, BackEnd #39 et Network #355 lorsque le
   quota le permettra ; intégrer humainement les révisions acceptées, puis
   repinner Workbench sur leurs commits intégrés. La PR #326 retire déjà
   `apps/silicium-ai-runtime` du tree courant si elle est acceptée ; aucun
   historique public n'est réécrit.
2. Garder les qualifications privées suspendues tant que quota et budget strict
   à zéro ne permettent pas une preuve sans dépassement. Les jobs différés restent
   bloquants pour toute livraison.
3. Conserver les livraisons désactivées pendant la qualification publique et
   la préparation des signatures et accès. L'ouverture du code n'est pas une
   qualification du candidat ni une acceptation de livraison.
4. Surveiller les dry-runs de synchronisation du Project, qui est déjà actif.
   Conserver les anciens automatismes jusqu'à validation de leur remplacement ;
   les transitions n'acceptent ni ne clôturent automatiquement une issue.
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

## Mise à jour vérifiée — 27 octobre 2026

Le dépôt public Workbench contient désormais les cinq sous-modules privés
Network, BackEnd, FrontEnd, DesktopApp et Solana. Le runtime d'inférence Python
local de DesktopApp était toutefois encore une copie ordinaire dans
`apps/silicium-ai-runtime`, donc présent dans l'arbre courant public. Une
correction séparée est préparée sur `lf-fix-210-ai-runtime-private` : les sources
ont été déplacées dans le dépôt privé DesktopApp, les chemins `include_str!` de
l'application ont été adaptés et le gitlink `apps/node` est repinné à
`6a233f1c421358143238c25562c45ad607b85721`.

Cette révision DesktopApp est la tête de la PR native #1, encore ouverte. Son
checkout Python isolé a passé 7 tests ; aucun check GitHub privé n'est rapporté,
car les Actions privées restent désactivées. L'accès aux composants et la
cohérence matérielle des cinq pins ont été vérifiés avant ce changement. Les
guides du composant Network ont été corrigés dans sa PR #355 aux commits
`012d7382` et `a7fdf8cc` ; le guide BackEnd a été corrigé dans la PR #39 au
commit `8bea9a87`. Les deux PR restent ouvertes et les Actions privées restent
désactivées. Cette branche Workbench aligne ses gitlinks et son verrou sur les
têtes de ces PR ; aucune CI privée, livraison, fusion ou activation de budget
n'est présumée. Les tests Rust et la compilation Tauri n'ont pas pu être exécutés
dans l'environnement local faute de toolchain Cargo/Rust.

La suppression du chemin dans un commit futur ne retire pas le code de
l'historique public déjà publié. Elle évite seulement que la révision courante
de Workbench continue de le distribuer. Les contrôles locaux disponibles
(`dev test --suite docs`, `git diff --check` et les 7 tests Python du runtime)
sont passés ; les tests Rust/Tauri restent impossibles localement sans Cargo.
La tête publiée `e0b103e` de la PR Workbench #326 a intégré `main` jusqu'à
`a20fcf2`. Son run public [40472945639](https://github.com/Silicium-Project/Workbench/actions/runs/40472945639)
a passé les contrôles publics et `ci/required` ; `validate` a été ignoré en scope
public. Ce résultat ne qualifie pas DesktopApp, BackEnd ou Network, et ne vaut
pas livraison. La PR #326 reste en brouillon jusqu'à l'acceptation des PR natives
et à la qualification privée correspondante. Le pin reste un candidat, pas une
version acceptée ou déployée.
