# Network

Ce projet fournit une image Docker optimisée basée sur Debian slim permettant de déployer un nœud **Silicium**, une surcouche (layer 2) reposant sur la blockchain Solana. L'image embarque les CLI Solana et Anchor ainsi qu'un script de gestion qui facilite le lancement d'un validateur connecté au testnet ou au mainnet Solana.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Construction de l'image

Construisez l'image Docker (l'installation des CLI se fait automatiquement) :

```bash
docker compose build
```

## Démarrage rapide d'un nœud Silicium

Le service par défaut de `docker-compose.yml` installe les dépendances et lance un validateur Solana configuré pour le réseau Silicium testnet.

```bash
docker compose up
```

Au premier démarrage, un couple de clés d'identité (et éventuellement de vote) est généré automatiquement et stocké dans `~/.config/solana` à l'intérieur du conteneur. Le ledger persiste sur votre machine dans `./data/ledger`.

## Choisir le réseau

Le script d'entrée expose la commande `silicium-node` avec un sous-ensemble d'options pratiques :

```bash
docker compose run --rm silicium-node silicium-node start --network mainnet
```

Les réseaux supportés sont :

- `testnet` (valeur par défaut, alias `SILICIUM_NETWORK=testnet`)
- `mainnet` (équivalent `mainnet-beta`)

Vous pouvez également transmettre d'autres options au binaire `solana-validator`, par exemple pour ouvrir un port RPC spécifique :

```bash
docker compose run --rm silicium-node \
  silicium-node start --network testnet --rpc-port 8899 -- --private-rpc
```

Toutes les variables suivantes peuvent être utilisées pour personnaliser l'exécution :

- `SILICIUM_LEDGER_DIR` : emplacement du ledger (par défaut `/home/solana/.silicium/ledger`).
- `SILICIUM_IDENTITY_PATH` : chemin du keypair d'identité (par défaut `~/.config/solana/validator-identity.json`).
- `SILICIUM_VOTE_ACCOUNT_PATH` : chemin du keypair de vote ; si absent, le nœud est lancé en mode observateur (`--no-voting`).
- `SILICIUM_RPC_PORT` et `SILICIUM_DYNAMIC_PORT_RANGE` : ports RPC et plage dynamique ouverts par le validateur.

## Utilisation du CLI

Le point d'entrée continue d'exposer le CLI Solana et Anchor. Quelques exemples :

```bash
# Exécuter une commande Solana simple
docker compose run --rm silicium-node solana balance

# Travailler avec Anchor
docker compose run --rm silicium-node anchor --version

# Ouvrir un shell bash dans l'image
docker compose run --rm silicium-node bash
```

Le volume monté sur `/workspace` donne accès aux fichiers du projet et permet d'utiliser le CLI comme si vous étiez sur votre machine locale.
