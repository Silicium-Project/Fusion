# Journal de veille

Les entrées ci-dessous sont préremplies à partir de l'historique du dépôt au
15 juillet 2026. La colonne « source externe » reste volontairement à compléter
par l'équipe avec les documents réellement consultés.

| Date | Sujet et question étudiée | Source externe consultée | Expérimentation / analyse | Conclusion appliquée | Preuve interne | Statut |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-07-14 | Fiabiliser la confirmation des transactions sur Solana Devnet | **À compléter** : URL exacte, titre, date de consultation | Observation du comportement de confirmation Devnet et adaptation du script de trace | Ajout d'un mécanisme de confirmation par polling HTTP | Commit `cff4c13`, script `solana-layer/scripts/devnet_trace_fragments.ts` | Source à compléter |
| 2026-07-14 | Éviter l'exposition de secrets dans les traces Devnet | **À compléter** | Relecture des données affichées et test des traces | Retrait de la clé Alchemy des traces | Commit `598f472` | Source à compléter |
| 2026-07-14 | Distribuer les fragments entre plusieurs nœuds sans délai excessif | **À compléter** | Essais multinœuds et tests automatisés du planificateur | Réclamations parallèles bornées et suppression de délais d'ordonnancement | Commits `faacf64`, `6db5678`; tests `tests/test_network_node.py` | Source à compléter |
| 2026-07-14 | Garantir qu'un fragment est vérifié indépendamment | **À compléter** | Ajout de scénarios automatisés autour de la vérification | Séparation entre exécution et vérification d'un fragment | Commit `d19efe1`; tests `tests/test_network_node.py` | Source à compléter |
| 2026-07-15 | Assurer l'équité des réclamations concurrentes du raytracer | **À compléter** | Tests de concurrence sur un workload réel | Ordonnancement équitable des tâches raytracer | Commits `e97dd53`, `1cb9e9e` | Source à compléter |
| 2026-07-15 | Rendre la traçabilité Devnet exploitable sans bloquer l'exécution | **À compléter** | Conception d'une trace compacte asynchrone et tests backend | Ajout d'une trace Devnet asynchrone visible dans le dashboard | Commit `e4f6713`; script `solana-layer/scripts/devnet_compact_trace.ts`; tests backend | Source à compléter |
| À dater | Encadrer le temps d'exécution, le CPU et la mémoire | **À compléter** | Définition de profils et seuils reproductibles | Budgets versionnés et contrôle strict possible en CI | `docs/performance-budgets.md`, `docs/performance-budgets.json`, `tools/perf_budget.py` | Mesures de référence à archiver |

## Modèle d'une nouvelle entrée

Copier cette section pour les sujets importants.

### AAAA-MM-JJ — Titre du sujet

- **Question :** problème technique précis à résoudre.
- **Sources :** titre, auteur/éditeur, URL, version, date de publication et date
  de consultation.
- **Fiabilité des sources :** documentation officielle, spécification, article,
  retour d'expérience ; signaler les éventuels conflits entre sources.
- **Hypothèse :** résultat attendu avant le test.
- **Expérimentation :** environnement, commande, données et protocole.
- **Résultat :** résultat brut, y compris en cas d'échec.
- **Décision :** technologie ou approche retenue, alternatives écartées et raison.
- **Application :** issue, PR, commit, test ou document associé.
- **Prochaine réévaluation :** date ou événement déclencheur (mise à jour majeure,
  changement d'API, régression, etc.).

