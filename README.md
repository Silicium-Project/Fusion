# Network

Cette base de code fournit une image Docker unique permettant de lancer un nœud **Silicium** (surcouche Solana) dans plusieurs contextes : localnet isolé, Devnet, Testnet ou Mainnet. Tout est orchestré via Docker Compose et un script d'entrée (`docker/solana-entrypoint.sh`) qui gère les clés, la configuration Solana et le lancement du validateur ou du test validator.

---

## Aperçu du dépôt

| Élément | Rôle |
| --- | --- |
| `Dockerfile` | Image basée sur `solanalabs/solana:stable`, ajout des CA TLS et du script d'entrée. |
| `docker-compose.yml` | Définit les services `silicium-localnet`, `silicium-node` (testnet), `silicium-devnet`, `silicium-mainnet`. |
| `docker/solana-entrypoint.sh` | Point d'entrée qui expose `solana`, `silicium-node` et configure automatiquement clés + RPC. |
| `data/` | Persistences des ledgers/clépairs (créé lors des premiers démarrages). |
| `README.md` | Ce document. |

---

## Prérequis

- [Docker Engine](https://docs.docker.com/get-docker/)
- [Docker Compose v2](https://docs.docker.com/compose/install/)

> Assurez-vous que votre utilisateur peut communiquer avec le daemon Docker (groupe `docker` ou exécution avec `sudo`).

---

## Construire l'image

```bash
docker compose build            # build standard
docker compose build --no-cache # rebuild complet (après changement d'entrypoint / Dockerfile)
```

---

## Services et modes disponibles

| Mode | Service | Commande de démarrage | Ports host | RPC cible (dans le conteneur) | Usage typique |
| --- | --- | --- | --- | --- | --- |
| Localnet | `silicium-localnet` | `docker compose up -d silicium-localnet` | `8900:8899`, `8100-8120` | `http://127.0.0.1:8899` | Dév hors ligne, tests rapides |
| Devnet | `silicium-devnet` (profil `devnet`) | `docker compose --profile devnet up -d silicium-devnet` | `8910:8899`, `8200-8220` | `https://api.devnet.solana.com` | Tests publics avec faucet |
| Testnet | `silicium-node` | `docker compose up -d silicium-node` | `8899:8899`, `8000-8020` | `https://api.testnet.solana.com` | Pré-production |
| Mainnet | `silicium-mainnet` (profil `mainnet`) | `docker compose --profile mainnet up -d silicium-mainnet` | `8920:8899`, `8300-8320` | `https://api.mainnet-beta.solana.com` | Production / observateur |

> Activez un profil en ajoutant `--profile devnet` ou `--profile mainnet` à toutes les commandes Compose (ou définissez `COMPOSE_PROFILES=devnet` dans votre shell).

---

## Démarrage rapide (Localnet)

```bash
# 1. Lancer le réseau local
docker compose up -d silicium-localnet

# 2. Consulter l'état
docker compose logs -f silicium-localnet

# 3. Ouvrir un shell dans le conteneur (CLI Solana déjà configuré)
docker compose exec silicium-localnet bash

# 4. Vérifier / interagir
solana config get
solana address
solana airdrop 100
solana balance
```

Pour arrêter et nettoyer :

```bash
docker compose down         # stoppe les services en cours
docker compose down -v      # supprime aussi les volumes (ledger, clés)
```

---

## Interagir avec Localnet, Devnet, Testnet ou Mainnet

1. **Lancer le service correspondant** (cf. tableau ci-dessus).
2. **Entrer dans le conteneur** en reprenant le même profil que lors du `up` :
   ```bash
   docker compose exec silicium-node bash                      # testnet
   docker compose --profile devnet exec silicium-devnet bash   # devnet
   docker compose --profile mainnet exec silicium-mainnet bash # mainnet
   ```
3. **Utiliser la CLI** (déjà pointée vers la bonne URL grâce au script d'entrée) :
   ```bash
   solana balance
   solana airdrop 1 <PUBKEY>    # disponible sur devnet/localnet uniquement
   solana transfer <DEST> 0.1
   solana program deploy target/deploy/app.so
   ```
4. **Depuis votre machine hôte ou un autre PC**, ciblez l'URL exposée :
   ```bash
   solana config set --url http://<ip-publique>:8900   # localnet exposé
   solana balance
   ```

---

## Gestion des clés et du CLI

- Au premier démarrage, `docker/solana-entrypoint.sh` génère un `validator-identity.json`, copie un signer par défaut dans `~/.config/solana/id.json` et alimente `solana config`.
- Pour créer un portefeuille dédié :
  ```bash
  docker compose exec silicium-localnet solana-keygen new --outfile /workspace/wallet.json
  docker compose exec silicium-localnet solana config set --keypair /workspace/wallet.json
  ```
- Pour récupérer la clé publique :
  ```bash
  solana-keygen pubkey /workspace/wallet.json
  ```

Les fichiers générés persistent via les volumes montés (`./data/...`). Sauvegardez-les avant toute suppression.

---

## Variables d'environnement principales

| Variable | Description |
| --- | --- |
| `SILICIUM_NETWORK` | `silicium`, `devnet`, `testnet`, `mainnet` (détermine RPC/entrypoints). |
| `SILICIUM_RPC_PORT` | Port RPC interne du validateur (ex: `8899`). |
| `SILICIUM_RPC_BIND_ADDRESS` | Adresse d'écoute (`0.0.0.0` pour accepter des clients distants). |
| `SILICIUM_DYNAMIC_PORT_RANGE` | Plage des ports dynamiques (vote, TPU…). |
| `SILICIUM_LEDGER_DIR` | Chemin du ledger dans le conteneur. |
| `SILICIUM_IDENTITY_PATH` / `SILICIUM_VOTE_ACCOUNT_PATH` | Emplacements des keypairs. |
| `SILICIUM_CLI_URL` | URL injectée dans `solana config set --url ...` à chaque démarrage. |
| `SILICIUM_PUBLIC_RPC_ADDRESS` | `host:port` annoncé via `--public-rpc-address`. |
| `SILICIUM_LOCAL_RESET` | `true` pour réinitialiser le ledger localnet au démarrage. |

Toutes les variables définies dans `docker-compose.yml` peuvent être surchargées via un fichier `.env` ou la ligne de commande (`SILICIUM_RPC_PORT=9000 docker compose up ...`).

---

## Exposer le réseau à d'autres machines

1. **Écoute externe** : gardez `SILICIUM_RPC_BIND_ADDRESS=0.0.0.0` et mappez les ports (`8899`, `8000-8020`, etc.) vers l'hôte.
2. **Pare-feu / Routeur** : ouvrez ou redirigez ces ports vers votre serveur.
3. **Annonce publique** : définissez `SILICIUM_PUBLIC_RPC_ADDRESS=mon-domaine.example.com:8899` pour informer les pairs du bon endpoint.
4. **Sécurité** : placez idéalement un reverse proxy TLS (Nginx, Caddy) ou un VPN (WireGuard) devant `8899` si l'accès doit être restreint.
5. **Clients distants** : communiquez l'URL (ex: `https://mon-rpc.example.com`) et demandez-leur d'exécuter `solana config set --url ...`.

---

## Troubleshooting de base

- `service "<name>" is not running` : relancez la commande avec le profil actif (`docker compose --profile devnet exec ...`) ou vérifiez `docker compose --profile devnet ps`.
- `certificate verify failed` : rebuild l'image (les CA sont installés dans le Dockerfile) et assurez-vous que la machine a accès au réseau.
- `airdrop request failed` sur testnet/mainnet : normal, seuls Devnet/Localnet disposent d'une faucet intégrée.
- Pour réinitialiser totalement la localnet : `docker compose down -v silicium-localnet`.

---

## Tests

Une suite Pytest couvre la logique du script d'entrée (sélection des réseaux, configuration du CLI, génération des clés).

```bash
pip install -r requirements-dev.txt
pytest
```

Les tests créent des stubs pour les binaires Solana, ils s'exécutent donc sans dépendances externes ni accès réseau, tout en validant les commandes critiques (lancement des nœuds, `solana balance`, `solana airdrop`, `solana transfer`, etc.).

---

## DSL de tests Silicium

La suite `tests/test_entrypoint.py` ne contient plus de valeurs en dur : elle lit `tests/testdata.txt`, un fichier texte facile à éditer ligne par ligne.

### Syntaxe

| Mot-clé | Rôle |
| --- | --- |
| `var <nom> <valeur>` | Définit un placeholder référencé par `${nom}` ailleurs dans le fichier. |
| `scenario <id>` / `end` | Début/fin d'un scénario. |
| `desc <texte>` | Description libre (affichée dans les logs Pytest). |
| `env <KEY> <value>` | Ajoute/écrase une variable d'environnement pour ce scénario. |
| `op ...` | Décrit l'opération lancée par l'entrypoint. Types disponibles : `start_network [network] [extra args...]`, `cli_command <program> [args...]`, `airdrop <amount> <dest> [flags...]`, `transfer <dest> <amount> [flags...]`. |
| `rule ...` | Assertion exécutée côté test (`expect_success`, `expect_failure`, `stderr_contains <txt>`, `log_contains <log> <snippet>`, `log_requires_entries <log>`, `file_exists <relative_path>`). |

### Exemple minimal

```txt
var urls.localnet http://127.0.0.1:8899

scenario localnet_uses_test_validator
desc Vérifie que le CLI pointe sur le RPC local
op start_network silicium
rule expect_success
rule log_contains solana config set --url ${urls.localnet}
end
```

Ajouter un scénario = copier/coller ce bloc, adapter `op` et les `rule`. Aucun changement Python nécessaire.

---

## Catalogue de calculs (`workloads/`)

Le dossier `workloads/` décrit les types de calcul que le réseau peut dispatcher.  
Pour chaque profil (encodage vidéo, simulation mathématique, inference IA, rendu, data processing) on fournit :

- un `manifest.yaml` machine-lisible (commande à exécuter, ressources nécessaires, artefacts attendus, règles de validation) ;
- un `README.md` expliquant le format des entrées/sorties et les recommandations matérielles.

Les devices téléchargent le manifest correspondant au job pour sélectionner le bon exécutable et reporter les preuves (hash, logs). Ajoutez vos propres profils en créant un nouveau sous-dossier dans `workloads/` puis en complétant les deux fichiers de référence.

Chaque manifest de calcul référence au moins une opération de vérification (`workloads/verification/...`). Lors du scheduling, seuls des noeuds n'ayant pas participé au calcul peuvent exécuter la vérification correspondante, garantissant une séparation stricte entre production et audit.

---

## Architecture on-chain Silicium (briques prévues)

| Programme | Responsabilité principale | Comptes clés |
| --- | --- | --- |
| **JobRegistry** | Enregistrement des jobs soumis via l'UI, escrow des SPL payés par les clients, suivi des fragments émis/réceptionnés. | PDA Job, coffre SPL, compte client. |
| **FragmentCertifier** | Enregistre chaque fragment calculé, stocke le hash/proof fournie par le node, valide la cohérence via un quorum ou une preuve externe. | PDA Fragment, compte du compute node (stake), références vers JobRegistry. |
| **ResultAssembler** | Agrège les fragments certifiés, publie le hash final et signale que le job est terminé (déblocage du paiement). | PDA Result, JobRegistry, comptes outputs (URI/IPFS). |
| **StakeManager** | Gestion du staking / réputation des compute nodes (collatéral en SPL, slashing en cas de fraude). | PDA Node, coffre staking, compte admin/gouvernance. |
| **Governance** | Paramètres protocolaires (frais, listes blanches de Program IDs custom, gestion des mises à jour). | Realm (p.ex. SPL Governance), comptes de votes. |

Flux simplifié : l'UI appelle JobRegistry pour créer un job + escrow SPL → les compute nodes réclament des fragments, les soumettent à FragmentCertifier → ResultAssembler valide que tous les fragments sont présents et signés → JobRegistry règle les nodes via StakeManager (bonus/malus). Cette découpe garde l'économie sous contrôle tout en permettant d'ajouter des “plugins” (programmes clients) via une liste blanche de Program IDs autorisés dans les CPI.

---

## Interface web & API (esquisse)

### Écrans principaux
1. **Dashboard client** : dépôt d'un job (upload artefacts, choisir ressources, budget SPL).  
2. **Suivi de job** : timeline des fragments, statut (file d'attente, en cours, agrégé), lien vers résultat final.  
3. **Compute node console** : enregistrement/staking, liste des tâches assignées, preuves soumises, récompenses.  
4. **Gouvernance** : votes sur mises à jour, limites économiques, programmes autorisés.

### API backend (REST/GraphQL minimal)
| Endpoint | Description |
| --- | --- |
| `POST /jobs` | Crée un job, renvoie l'instruction Solana à signer pour JobRegistry + métadonnées IPFS/S3. |
| `GET /jobs/:id` | Statut agrégé (on-chain + off-chain). |
| `POST /nodes/register` | Fournit l'instruction StakeManager à signer (stake, KYC éventuel). |
| `POST /fragments/:id/proof` | Upload de la preuve + signature qui seront ensuite poussées on-chain via FragmentCertifier. |
| `GET /governance/proposals` | Liste synchrone avec le programme de gouvernance. |

Le backend agit comme “indexeur” : il surveille les programmes Solana (via WebSocket RPC ou service type Helius), stocke les évènements pour l'UI, et prépare les transactions que les utilisateurs signeront dans leur wallet.

---

## Checklist exploitation Mainnet

1. **Clés & secrets** : générer les keypairs validator/vote sur une machine hors-ligne, les injecter via volumes chiffrés, conserver des sauvegardes scellées.  
2. **Monitoring** : activer Prometheus/Grafana ou au minimum `solana-validator --log` + alertes (RAM, vote distance, skipped slots).  
3. **Réseau** : ouvrir uniquement les ports nécessaires (8899 + plage TPU), placer un reverse proxy TLS pour le RPC public, limiter les IP si besoin.  
4. **Mises à jour** : script de rolling upgrade (arrêt propre, sauvegarde ledger, mise à jour Docker image, redémarrage, vérification `solana-validator monitor`).  
5. **Sécurité applicative** : valider chaque nouvelle version des programmes on-chain (audit interne ou externe), publier les Program IDs et procédures de migration.  
6. **Plan de reprise** : documenter la restauration à partir des backups (keypairs, snapshot Solana, configuration Docker), tester régulièrement.

---

## Aller plus loin

- Automatisez vos déploiements prod en injectant vos clés validator/vote via des volumes chiffrés.
- Ajoutez un observateur ou un RPC privé en passant les flags Solana supplémentaires après `--` dans `command`.
- Contribuez au script d'entrée pour gérer d'autres profils (clusters internes, entrypoints custom).
