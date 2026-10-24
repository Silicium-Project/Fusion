# Gestion des issues et du travail Silicium

Le pilotage des quatre dépôts se fait dans un seul [GitHub Project](https://github.com/orgs/Silicium-Project/projects/12).
La [direction du programme](https://github.com/Silicium-Project/Fusion/issues/208) fixe les invariants ; le Project porte l'état courant.

## Ce que chaque objet signifie

| Objet | Usage |
| --- | --- |
| Programme | Direction, garanties, navigation et arbitrages. |
| Phase R0–R9 | Capacité à obtenir et condition de sortie ; peut avancer en parallèle d'une autre phase. |
| Spécification | Contrat détaillé, critères, risques et catalogue de validation. |
| Issue d'exécution | Livrable borné à une PR cohérente, avec oracle de validation. |
| Milestone | Qualification d'un lot dans un dépôt ; les milestones R0–R9 sont coordonnées par les phases transverses. |
| Arbitrage | Question nécessitant une décision explicite ; hors travail engagé. |

Les dépendances de sûreté et d'intégration restent obligatoires. Une tranche documentaire ou d'inventaire peut commencer avant sa spécification parente si elle ne modifie aucun comportement qui en dépend.

## Une information, un emplacement

- **Status, Urgence, Horizon, Phase, Niveau et Size** : champs du Project commun.
- **Responsable** : assignation native de l'issue ; une personne responsable d'une issue engagée.
- **Domaine** : labels `area:*` ; ne pas créer une seconde taxonomie équivalente.
- **Type de demande** : types natifs Bug, Feature ou Task. Investigation et décision sont distinguées dans le formulaire et le titre.
- **Parents et prérequis** : relations natives de sous-issue et de dépendance, avec URL complète entre dépôts.
- **Acceptation et preuves** : corps de l'issue et commentaire final de qualification.

Les anciens labels `status:planned` et `priority:P*` du backlog réaligné sont retirés pour éviter une seconde source d'état. L'ancien champ Priority du modèle de Project n'est pas le champ de pilotage : utiliser **Urgence** dans les vues communes.

## Cycle de travail

`À qualifier → Backlog → Prêt → En cours → Revue → Validation → Terminé`

| Passage | Conditions |
| --- | --- |
| À qualifier → Backlog | Besoin compris, dépôt compétent, doublons vérifiés et décision de conserver la demande. |
| Backlog → Prêt | Périmètre borné, critères d'acceptation, tests/oracles attendus, dépendances applicables satisfaites et responsable. |
| Prêt → En cours | Travail effectivement commencé, branche liée ; une seule implémentation active par personne pour commencer. |
| En cours → Revue | PR prête à relire, auto-relecture et preuves disponibles ; contrôles pertinents verts. |
| Revue → Validation | Changement intégré ou livrable accepté en revue ; qualification restante explicitée. |
| Validation → Terminé | Critères satisfaits, preuves liées aux SHA exacts et limites connues documentées. |

Une PR fusionnée ne suffit pas à terminer une issue. Le responsable place manuellement l'issue en **Validation** après fusion ; il ne la clôt qu'après acceptation. Un défaut découvert pendant la qualification renvoie l'issue vers En cours ou Backlog avec une explication.

Le blocage est une relation ou un motif documenté, pas un état qui efface l'étape réelle. Ajouter le prérequis avec **Relationships → Mark as blocked by**. Pour un blocage externe, ouvrir une décision ou une tâche de résolution avec responsable et prochaine action. Aucun timeout ne transforme un calcul non vérifié en résultat final.

## Prêt à commencer

Avant d'engager une issue d'exécution :

- [ ] Objectif unique et livrable vérifiable, adapté à une PR relisible.
- [ ] Dépôt, chemins, consommateurs et commit de départ vérifiés.
- [ ] Préconditions et dépendances explicites ; aucune décision d'architecture cachée.
- [ ] Critères d'acceptation et oracle indépendant définis.
- [ ] Méthode de validation proportionnée : unitaire, intégration, adversarial, E2E ou revue documentaire selon le changement.
- [ ] Risques de sécurité, compatibilité, migration et restauration traités lorsqu'ils s'appliquent.
- [ ] Responsable identifié ; estimation XS/S/M indicative. Un L/XL doit être redécoupé avant exécution.

Ne pas forcer toutes les spécifications du programme dans ce format dès maintenant : créer les tranches quand elles approchent du début du travail.

## Définition de terminé

- [ ] Chaque critère d'acceptation est satisfait ou son changement a été décidé et tracé.
- [ ] PR et commits exacts liés ; composition Fusion identifiée pour un changement intercomposants.
- [ ] Vérifications pertinentes réussies, avec commandes, environnement et résultats réels. Un test prévu n'est pas un test exécuté.
- [ ] Tests négatifs/adversariaux et non-régression ajoutés si le comportement l'exige ; aucune garantie de sûreté affaiblie pour réduire la latence.
- [ ] Documentation, contrats et migrations mis à jour lorsqu'ils sont concernés.
- [ ] Déploiement ou parcours réel qualifié lorsque le critère porte sur l'environnement livré ; une compilation ne prouve pas un déploiement.
- [ ] Limites, risques résiduels et suites restantes explicités. Un simple constat statique ne certifie pas le runtime.

Une phase est terminée après sa synthèse de qualification, pas au seul pourcentage de sous-issues fermées. Les issues historiques déjà fermées sont conservées comme historique ; le nouveau workflow ne les recertifie pas rétroactivement.

## Urgence et horizon

| Urgence | Sens |
| --- | --- |
| P0 | Incident ou blocage immédiat confirmé, avec impact, responsable et condition de sortie. |
| P1 | Fondation ou prochain travail important ; sélectionner selon les prérequis et l'horizon. |
| P2 | Travail prévu après les fondations ; pas d'engagement implicite. |
| P3 | Extension ou exploration conditionnelle. |

La criticité de sécurité et l'urgence d'exécution sont différentes : les exigences de sûreté restent obligatoires même sur un ticket qui n'est pas P0.

**Maintenant / Ensuite / Plus tard** ordonnent les objectifs. Maintenant ne rend pas toute une spécification prête. Une date ou une itération n'est ajoutée qu'après engagement ; ne pas inventer des échéances pour remplir une frise.

## Vues et revue courte

1. **À faire maintenant** : les tranches prêtes, avec responsable.
2. **Tableau de travail** : Prêt, En cours, Revue et Validation ; surveiller le travail simultané.
3. **Backlog** : spécifications et prochaines tranches, ordonnées après triage.
4. **Roadmap** : phases, horizon et progression.
5. **Blocages** : prérequis ouverts et action nécessaire pour avancer.
6. **Arbitrages** : décisions en attente, y compris les anciennes demandes conservées.
7. **Validation** : travail relu ou intégré en attente de qualification.

Chaque semaine : trier les entrées, traiter les blocages, vérifier l'âge des travaux engagés et préparer quelques prochaines tranches. Revoir les horizons et arbitrages toutes les deux semaines ou après un changement de direction.

Suivre le délai de réalisation, le temps bloqué, l'âge des travaux actifs, les réouvertures et les défauts découverts après qualification. Un nombre d'issues fermées ou un pourcentage de couverture ne suffit pas à mesurer la qualité. Ces mesures ne sont annoncées comme disponibles qu'après instrumentation.

## Automatisation sobre et droits

Les formulaires ciblent `Silicium-Project/12`. GitHub exige que la personne qui crée l'issue ait le droit d'écriture sur ce Project pour cet ajout automatique. Les sous-issues d'un parent déjà présent bénéficient de l'automatisation native d'ajout.

Une issue créée hors formulaire ou par un contributeur sans ce droit doit être ajoutée au triage par un mainteneur :

```sh
gh project item-add 12 --owner Silicium-Project --url https://github.com/Silicium-Project/REPO/issues/NUMERO
```

L'offre Free limite le nombre de règles natives d'ajout par Project. Ce fonctionnement n'exige ni nouveau secret, ni robot de compilation, ni tâche sur le VPS. L'ajout via API ne doit pas être supposé automatique hors de ces parcours.

Le passage fusion → Terminé a été retiré. Les transitions qui attestent l'acceptation restent une décision humaine traçable. Les anciens Projects sont conservés fermés avec un lien vers le tableau commun ; leur historique n'est pas supprimé.

## Branches et PR

Le flux applicatif reste une branche de travail → PR vers `dev` → qualification → promotion contrôlée vers `main`.
Utiliser un nom comme `issue/240-invariants-finalite`. Lier chaque PR avec **Refs** et l'URL complète ; éviter **Closes/Fixes/Resolves** tant que la fusion n'est pas à elle seule le critère d'acceptation. Relier les PR entre dépôts pour un changement de contrat.

Les formulaires GitHub sont lus depuis la branche par défaut. Leur première mise en service peut donc demander une PR de métadonnées basée sur cette branche : elle doit être limitée à la documentation et aux modèles, relue, et ne doit pas promouvoir les changements applicatifs de dev.

Sources : [GitHub Projects](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/best-practices-for-projects), [formulaires](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms), [dépendances](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies).
