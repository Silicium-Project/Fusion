# Network

Ce projet fournit un conteneur Docker prêt à l'emploi contenant le Solana CLI. Il vous permet d'exécuter des commandes Solana sans rien installer sur votre machine.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Démarrage rapide

1. Construisez l'image Docker (celle-ci installe automatiquement les CLI Solana et Anchor) :
   ```bash
   docker compose build
   ```
2. Vérifiez la version du CLI Solana :
   ```bash
   docker compose run --rm solana-cli --version
   ```
3. Vérifiez que l'outil Anchor est également disponible :
   ```bash
   docker compose run --rm solana-cli anchor --version
   ```

> **Remarque :** si vous n'utilisez pas le plugin Docker Compose V2, remplacez `docker compose …` par `docker-compose …` dans les commandes ci-dessus.

## Utilisation interactive

Le conteneur a pour point d'entrée un script qui invoque `solana` par défaut. Vous pouvez donc lancer n'importe quelle sous-commande directement :

> Les exemples suivants utilisent la syntaxe Docker Compose V2 (`docker compose`). Avec Docker Compose V1 (sans le plugin V2), remplacez simplement `docker compose` par `docker-compose`.

```bash
docker compose run --rm solana-cli balance
```

Pour ouvrir un shell bash dans le conteneur tout en conservant l'accès au CLI :

```bash
docker compose run --rm solana-cli bash
```

Les commandes Anchor fonctionnent de la même manière, par exemple pour créer un nouveau projet :

```bash
docker compose run --rm solana-cli anchor init mon-projet
```

Tout autre binaire présent dans l'image (comme `sh` ou `ls`) peut être exécuté de la même manière, tandis que les options commençant par `-` sont transmises automatiquement au CLI Solana.

Le volume monté sur `/workspace` vous permet d'accéder aux fichiers du projet depuis l'intérieur du conteneur.
