# Network

Ce projet fournit un conteneur Docker prêt à l'emploi contenant le Solana CLI. Il vous permet d'exécuter des commandes Solana sans rien installer sur votre machine.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Démarrage rapide

1. Construisez l'image Docker :
   ```bash
   docker compose build
   ```
2. Vérifiez la version du CLI Solana :
   ```bash
   docker compose run --rm solana-cli --version
   ```

## Utilisation interactive

Le conteneur a pour point d'entrée un script qui invoque `solana` par défaut. Vous pouvez donc lancer n'importe quelle sous-commande directement :

```bash
docker compose run --rm solana-cli balance
```

Pour ouvrir un shell bash dans le conteneur tout en conservant l'accès au CLI :

```bash
docker compose run --rm solana-cli bash
```

Tout autre binaire présent dans l'image (comme `sh` ou `ls`) peut être exécuté de la même manière, tandis que les options commençant par `-` sont transmises automatiquement au CLI Solana.

Le volume monté sur `/workspace` vous permet d'accéder aux fichiers du projet depuis l'intérieur du conteneur.
