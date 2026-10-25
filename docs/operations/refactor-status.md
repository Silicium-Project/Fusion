# Refonte : état de référence et conditions d'activation

Cette page décrit les livrables préparés dans la branche d'intégration. La
[PR centrale #317](https://github.com/Silicium-Project/Fusion/pull/317) porte
les résultats du dernier commit. Ni cette page ni une qualification de PR
n'autorisent une fusion, une acceptation ou une livraison.

## Décisions conservées

- Fusion reste **privé**, sur décision du propriétaire le 25 octobre 2026.
- Aucune dépense Actions supplémentaire ; arrêt des dépassements à zéro.
- Les six anciennes inscriptions de runners VPS sont retirées. Aucun build,
  test ou packaging ne revient sur le VPS.
- Le checkout initial et ses changements restent conservés. Les travaux sont
  préparés dans une copie isolée, avec sauvegardes et carte de provenance.
- Aucun programme, wallet ou autorité Solana n'est remplacé par cette refonte.

## Lots et preuves attendues

| Lot | Livrable préparé | Condition restant à démontrer ou décider |
|---|---|---|
| L0 | Références Git et GitHub, sauvegardes des historiques, patchs et fichiers locaux, inventaire des CI et runners | Conserver l'inventaire privé comme référence de restauration ; actualiser les nouvelles preuves |
| L1 | Audit d'exposition, formulaires communs, HOLD isolés, contribution et consignes IA | Nouvelle approbation explicite avant toute ouverture ; confirmer la provenance des visuels |
| L2 | Historiques importés sans squash, gitlinks retirés, chemins corrigés, issues et relations transférées | Revue indépendante des PR ; qualification complète du dernier commit avant intégration |
| L3 | Procédure d'ouverture, outils de protection et retrait des anciens runners | **Reporté par le propriétaire** ; aucun changement de visibilité |
| L4 | `dev`/`dev.ps1`, registre, routage, contrôle final, normes, diagnostics et métriques | Résultat GitHub complet du commit évalué et parcours Windows/Anchor ; voir les checks de la PR |
| L5 | Construction sur GitHub, manifeste, signatures et snapshots, tests d'installation, application et rollback API/web | Provisionner les signatures/SSH, qualifier installations et mises à niveau, adopter le VPS et démontrer le rollback ; drainage/canari runtime toujours bloquants |
| L6 | Champs du Project, moteur de réconciliation, acceptation avec preuves et procédures IA | Créer/installer l'App, qualifier ses droits et son exécution avant activation et retrait des automatismes natifs |

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

Le run a exécuté notamment 151 tests Go, 112 unités web et 56 scénarios
navigateur, 34 unités natives Linux, 323 tests runtime et 69 tests WASM. Les
trois scénarios P2P existants et 22 tests Python réseau ont passé. Ces scénarios
ne prouvent pas toutes les fonctionnalités futures de délégation organique.

Le moteur Project a été exécuté **sans écriture** sur les 134 issues actives :
32 éléments du dépôt privé d'arbitrage sont restés exclus. Les transitions
proposées et blocages restent un diagnostic, sans acceptation ni clôture.

Les résultats d'installation APT/DNF/NSIS, de canari et de rollback ne sont
pas encore fournis par une livraison réelle. Un rendu Compose ou des tests
unitaires de scripts ne remplacent pas ces preuves.

## Activation restante, dans l'ordre

1. Achever la qualification du commit, demander la revue indépendante et
   traiter les commentaires avant une intégration humaine.
2. Conserver les livraisons désactivées tant que la préparation et la décision
   d'ouverture restent en attente. Une fenêtre privée ponctuelle n'autorise que
   les validations de sa PR et de son SHA.
3. Créer l'App de suivi avec le manifeste fourni, sans recopier le jeton CLI
   dans Actions. Vérifier le mode lecture avant toute synchronisation active.
4. Rétablir la clé d'auto-update correspondant à celle des clients, ou qualifier
   une migration de confiance revue. La dérive constatée reste bloquante.
5. Provisionner les environnements de signature et déploiement par un canal
   sécurisé ; qualifier les paquets et leur mise à niveau sur GitHub.
6. Adopter les artefacts actuellement servis comme référence de rollback,
   préserver volumes et identités et retirer le publisher historique.
7. Qualifier drainage, canari et reprise avant tout changement d'image réseau.
   Une télémétrie absente ou un simple healthcheck n'autorisent pas un arrêt.
8. Démontrer dev, promotion prod et rollback, puis demander les acceptations
   humaines des issues de gouvernance/CI/QRE concernées.

Voir [l'activation détaillée](bootstrap.md), [la livraison](delivery.md),
[la revue d'exposition](exposure-review.md) et [les parcours IA](../ai/README.md).
