# Diagnostiquer les services et le VPS

## Commencer par les lectures

```sh
./dev ops diagnose --environment dev --json
./dev ci inspect --run ID --json
```

La première commande prépare une demande sans l'exécuter. Avec `--apply`,
elle lance `diagnostics.yml` sur GitHub, après contrôle des droits. Elle refuse
l'exécution tant que Fusion reste privé et que les workflows sont suspendus.
L'environnement production garde son approbation humaine.

Le rapport `host-diagnostics-dev` expire après un jour. Il contient la charge
CPU observée pendant une seconde, l'espace disque, les conteneurs du canal,
leur consommation et les codes de santé HTTP. Le contrôle RPC Devnet émet un
seul `getHealth`, borné à cinq secondes. Un HTTP 429 est identifié ; un JSON-RPC
en erreur avec HTTP 200 ne devient pas un succès. L'absence de données reste
signalée comme indisponible.

## Droits et limites

Le script `infra/delivery/diagnostics.py` doit être installé par l'adoption
revue comme `/usr/local/sbin/silicium-diagnose`, détenu par root et non
modifiable par `silicium-deploy`. Sudo autorise cette entrée uniquement avec
`--channel dev` ou `--channel prod`. La clé et les hôtes SSH sont les valeurs
protégées de l'environnement ; aucune découverte de clé SSH automatique.
L'activation exige aussi `SILICIUM_DIAGNOSTICS_ENABLED=1`.

Le script ne lit ni fichiers d'environnement, ni clés, ni wallets, ni logs
applicatifs. Il ne redémarre aucun service et n'exécute aucun build ou test.
Les campagnes de charge restent sur GitHub. Une seconde de CPU n'est pas une
mesure p95 ; conserver plusieurs observations pour rechercher une saturation.

## Reprise

Une erreur SSH, une entrée sudo absente ou un rapport invalide fait échouer le
workflow. Corriger l'installation ou les droits via la procédure d'adoption,
puis relancer une seule observation. Une saturation RPC ne justifie ni un
redémarrage des workers ni une baisse des règles de validation P2P.

Les tests `tests/test_diagnostics.py` vérifient les calculs, le canal et les
commandes permises ; ils ne constituent pas une observation du VPS.
