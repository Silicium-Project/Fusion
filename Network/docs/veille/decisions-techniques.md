# Synthèse des décisions techniques

Cette synthèse prépare le discours oral. Les sources externes doivent être reliées
aux entrées correspondantes du journal avant la soutenance.

## Solana et Anchor pour la traçabilité

**Besoin.** Conserver un état vérifiable des jobs, fragments, validations et
récompenses sans déposer les fichiers lourds directement sur la chaîne.

**Choix appliqué.** Un programme Anchor porte l'état et les transitions on-chain ;
le SDK TypeScript stabilise l'accès pour le backend, le frontend, les workers et
les futurs indexeurs. Les contenus lourds restent hors chaîne et sont référencés
avec les métadonnées nécessaires à leur vérification.

**Alternatives à documenter.** Base centralisée seule, contrat sur une autre
chaîne, écriture de toutes les données on-chain. Pour chacune, ajouter les critères
réellement évalués : coût, débit, finalité, outillage, complexité et maintenabilité.

**Preuves.** Documentation complète du layer Solana, README du SDK, scripts de
trace Devnet et commits liés à la confirmation.

## Polling HTTP pour confirmer les opérations Devnet

**Problème observé.** Le parcours de trace Devnet nécessitait une confirmation
plus robuste.

**Choix appliqué.** Le script utilise un suivi HTTP pour fiabiliser la confirmation.

**Preuve.** Commit `cff4c13` et évolution de
`solana-layer/scripts/devnet_trace_fragments.ts`.

**Limite.** La décision ne peut être attribuée à une source de veille particulière
tant que l'URL et la date de consultation ne sont pas inscrites dans le journal.

## Réclamations parallèles bornées

**Problème observé.** Le traitement multinœud subissait des délais et devait éviter
qu'une concurrence non limitée dégrade la stabilité ou l'équité.

**Choix appliqué.** Autoriser un parallélisme borné, puis corriger l'équité du
planificateur sur le workload raytracer.

**Preuves.** Commits `faacf64`, `6db5678`, `e97dd53` et `1cb9e9e`, accompagnés
des scénarios de `tests/test_network_node.py`.

**Mesure encore nécessaire.** Archiver des résultats comparables avant/après :
durée totale, débit de fragments, latence p50/p95, taux d'échec, nombre de nœuds et
limite de concurrence.

## Vérification indépendante des fragments

**Risque.** Une validation effectuée par le même acteur que l'exécution affaiblit
la confiance dans le résultat distribué.

**Choix appliqué.** Imposer l'indépendance de la vérification dans le planificateur.

**Preuve.** Commit `d19efe1` et scénarios automatisés associés.

**À compléter.** Référencer la source externe ou le modèle de menace ayant motivé
le choix, puis préciser les compromis de disponibilité et de latence.

