# Workbench CI snapshot — 27 octobre 2026

Instantané horodaté et données détaillées : [`ci-workbench-metrics-2026-10-27.json`](ci-workbench-metrics-2026-10-27.json). Il couvre les 20 runs les plus récents du workflow CI public Workbench. Il ne prouve pas la qualification des composants privés.

## Mesures observées

| Indicateur | Échantillon | Médiane | p95 |
|---|---:|---:|---:|
| Run CI complet | 20 runs | 1 min 57 s | 2 min 18 s |
| Retour des jobs rapides | 20 runs | 1 min 37,5 s | 1 min 55 s |
| Attente/provisionnement par job | 140 jobs | 4 s | 5 s |
| Exécution par job | 140 jobs | 20 s | 1 min 5 s |

Les 20 runs étaient réussis au moment de la capture. Les 20 rapports de cache étaient disponibles : 20 hits, aucun miss. Les artefacts actifs listés totalisaient 805 350 octets. Les définitions, SHA et URL des runs figurent dans le JSON associé.

Le run CI de la PR [#326](https://github.com/Silicium-Project/Workbench/pull/326) est représentatif du périmètre public : `ci/required` a réussi et `validate` a été ignoré, car les sources des composants sont privées. Ce résultat ne qualifie ni les composants ni le workflow Integration.

## Suite Solana

Le run [40223122663](https://github.com/Silicium-Project/Workbench/actions/runs/40223122663) a réussi ; son job `validate (solana, ubuntu-24.04, 45)` a duré **790 secondes** (13 min 10 s). C’est une observation isolée, mesurée le 25 octobre, hors de l’échantillon du 27 octobre. Les tests localnet restent requis lorsqu’un changement touche Solana.

Le cache Cargo de registre est actif, tandis que la sauvegarde du répertoire Rust `target` reste désactivée pour la suite Solana. L’inventaire des caches relevé le 27 octobre comptait 79 entrées / 6 185 088 793 octets dans Workbench et 18 entrées / 9 144 183 415 octets dans Network. Les caches sont séparés par dépôt ; la faible marge observée dans Network ne justifie pas d’y ajouter une compilation SBF volumineuse sans mesure.

## Décision de suivi

- Le retour rapide de Workbench respecte l’objectif initial inférieur à cinq minutes à chaud. Aucun contrôle obligatoire n’est à retirer pour améliorer ce chiffre.
- Garder l’App **Silicium Source Reader** pour l’accès `Contents: read` aux dépôts composants. Une App supplémentaire « Actions Reader » n’est pas nécessaire au workflow Integration actuel : `qualification.yml` et `private-delivery-preflight.yml` demandent déjà `actions: read`, et les téléchargements utilisent `github.token` sur les artefacts du même dépôt Integration.
- Ne pas activer globalement le cache Rust `target` sur la seule base d’un run lent. Si l’optimisation reste prioritaire, faire un essai isolé et mesurer taille, hit au second run, durée et évictions avant de le garder.
- Garder distincts les résultats publics et privés. Aucun run de qualification privée Integration n’a encore été observé ; les lanes de livraison restent indépendamment fermées.

La charge et les durées sont des mesures GitHub observées. Elles ne donnent pas le solde de minutes incluses ni ne prouvent l’absence de frais pour un autre dépôt privé.
