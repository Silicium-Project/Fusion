# Infrastructure et livraison

Les workflows GitHub construisent et qualifient les composants. Le VPS reçoit
un manifeste signé et applique des artefacts identifiés par digest.

- [Livraison et limites d'activation](../docs/operations/delivery.md)
- [Adoption du VPS et secrets](../docs/operations/bootstrap.md)
- [Commandes communes](../docs/development/commands.md)
- [Instructions infrastructure](AGENTS.md)

`compose/docker-compose.yml` et `compose/dev-miniworkers.yml` n'ont aucun build.
Les entrées historiques de build/publication sur le VPS retournent une erreur.
Les outils VPN restent utilisables ; les procédures historiques de création de
runners ne doivent plus être utilisées. Ne pas interrompre un worker sans
protocole de drainage qualifié.
