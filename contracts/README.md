# Contrats partagés

- `http/api.openapi.yaml` : API publique Go ; consommateurs web et clients.
- `ci/` : plans, preuves de validation et manifestes de livraison versionnés.
- `workspace/registry-v1.schema.json` définit l’identité, les propriétaires,
  les dépôts, les chemins et les suites des composants ;
  `workspace/pins-v1.schema.json` définit les commits intégrés.
- `ci/repository-policy-report-v1.schema.json` définit le rapport d’audit
  public du dépôt et les horodatages servis par l’API GitHub.
- Le protocole P2P est documenté dans `network/docs/contracts`.
- L'IDL Solana est dérivée du programme de `chain/solana`, vérifiée avec le SDK
  et conservée comme artefact du build qualifié.

Un changement de contrat doit qualifier ses producteurs et consommateurs.
Aucune conversion de montant, unité de travail ou version n'est déduite d'une
valeur absente. Les nouveaux champs de métadonnées restent additifs.
