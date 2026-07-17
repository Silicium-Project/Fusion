# Dossier de veille technologique — Silicium

Ce dossier rassemble les preuves de la veille technique du projet. Son objectif
est de démontrer une chaîne vérifiable :

> source consultée → analyse → expérimentation → résultat → décision → intégration

## Contenu

- [`../roadmap-2026-2027.md`](../roadmap-2026-2027.md) : roadmap consolidée,
  défis techniques, risques, priorités et indicateurs de pilotage ;
- [`journal-veille.md`](journal-veille.md) : registre chronologique des sujets
  étudiés et de leur impact sur Silicium ;
- [`registre-preuves.md`](registre-preuves.md) : liens vers les commits, tests,
  scripts et documents qui prouvent l'application de la veille ;
- [`decisions-techniques.md`](decisions-techniques.md) : synthèse des choix et de
  leurs alternatives ;
- [`modele-benchmark.md`](modele-benchmark.md) : protocole reproductible pour
  conserver les mesures avant/après.

## Comment utiliser ce dossier

Pour chaque nouvelle recherche :

1. ajouter une ligne datée dans le journal ;
2. conserver le lien exact et la date de consultation de la source ;
3. résumer l'information avec ses propres mots ;
4. décrire le test ou prototype réalisé ;
5. relier la conclusion à une issue, une PR, un commit ou une décision ;
6. joindre les mesures brutes lorsqu'une affirmation porte sur la performance.

Une entrée n'est considérée comme complète que si la source externe et la preuve
interne sont toutes les deux renseignées. Un commit prouve l'application d'une
décision, mais ne prouve pas à lui seul la veille qui l'a précédée.

## Pièces à présenter au jury

Sélection recommandée en annexe de la présentation :

- une page du journal comportant des sources datées ;
- une décision technique avec ses alternatives ;
- une trace Devnet ou un résultat de test ;
- un benchmark avant/après avec la configuration de la machine ;
- le commit ou la PR ayant intégré la conclusion dans le produit.

## Contrôle avant soutenance

- [ ] Chaque URL est accessible et correspond à une source réellement consultée.
- [ ] Les dates de consultation sont présentes.
- [ ] Les affirmations de performance reposent sur des résultats bruts conservés.
- [ ] Les hashes de commits existent dans l'historique Git présenté.
- [ ] Les limites et résultats négatifs sont également documentés.
- [ ] Les informations sensibles sont retirées des captures et traces Devnet.
