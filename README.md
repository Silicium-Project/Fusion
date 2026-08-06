# Silicium

Silicium regroupe le reseau de calcul distribue, le layer Solana Devnet, le dashboard d'observation et le site client.

Les composants Network, BackEnd et FrontEnd sont suivis comme submodules Git pour garder leur cycle de vie independant tout en restant composes par Fusion.

Le plan d'attaque fige, le tri actif/transition/vestige et le topologie CI/CD
canonique sont documentes dans:

- [docs/repo-attack-plan-and-triage.md](docs/repo-attack-plan-and-triage.md)
- [docs/ci-cd-topology.md](docs/ci-cd-topology.md)

Le chemin operatoire visible dans GitHub est maintenant simple: `Build`,
`Test`, puis `Deploy`, tous relies a l'execution VPS/self-hosted.

Fusion conserve des SHA exacts afin que chaque build, rollback et deploiement soit
reproductible. Le workflow `Sync submodule gitlinks` compare toutes les cinq
minutes les branches declarees dans `.gitmodules`, publie une composition exacte
sur `main`, puis declenche explicitement les pipelines CI/CD consommateurs. Le
workflow `submodule-ci-gate` bloque aussi Fusion si le head `main` de l'un des
submodules `BackEnd`, `FrontEnd` ou `Network` est rouge, en attente ou incomplet;
la composition ne peut donc pas avancer sur une branche sous-module deja cassee.
Il ne faut pas remplacer ce mecanisme par un `git submodule update --remote`
pendant le deploiement: le contenu deploye ne correspondrait alors plus au
commit Fusion audite.

Le workflow utilise la GitHub App Silicium en lecture seule pour cloner les
depots prives. La publication du gitlink sur `main` peut utiliser soit un token
ecriture configure dans `SILICIUM_SYNC_PUSH_TOKEN`, soit une deploy key SSH
configuree dans `SILICIUM_SYNC_DEPLOY_KEY`; `SILICIUM_SYNC_DEPLOY_KNOWN_HOSTS`
peut etre fourni pour pinning explicite. Si aucun secret de publication n'est
defini, le workflow s'arrête avec une erreur explicite.

## Installation locale Windows

Depuis la racine du repository:

```powershell
git clone --recurse-submodules https://github.com/Silicium-Project/Fusion.git
.\install-silicium-windows.cmd -InstallSystemDeps
```

Si le repository a ete clone sans recurse-submodules, lancez d'abord:

```powershell
git submodule update --init --recursive
```

Ce script verifie/installe les outils systeme principaux, puis installe les dependances npm du dashboard Devnet, du layer Solana et du site.

## Lancement local en une commande

Depuis la racine du repository:

```powershell
.\start-silicium-local.cmd
```

Le lancement local suppose que les submodules sont initialises.

Le script demarre:

- les noeuds demo P2P `worker-1` et `verifier-1`;
- une base SQLite locale dans `.silicium\site\silicium.db` par defaut;
- le dashboard Devnet local sur `http://localhost:5174/`;
- le service BackEnd sur `http://localhost:8080`;
- le service FrontEnd sur `http://localhost:3000/dashboard`.

Les logs sont ecrits dans `.silicium\logs\local-start`.

Options utiles:

```powershell
.\start-silicium-local.cmd -Visible
.\start-silicium-local.cmd -DryRun
.\start-silicium-local.cmd -SkipDatabase
.\start-silicium-local.cmd -SkipBackend
```

`-Visible` ouvre une fenetre par service. `-DryRun` affiche les commandes sans rien demarrer.

## Variables locales importantes

Le backend lit notamment:

- `DATABASE_URL`, avec une valeur locale par defaut PostgreSQL si absente;
- `DATABASE_DRIVER`, `sqlite` en local par defaut, `postgres` pour une vraie DB;
- `SQLITE_PATH`, avec `.silicium\site\silicium.db` par defaut;
- `JWT_SECRET_KEY`, avec une valeur locale de developpement si absente;
- `SILICIUM_NETWORK_ROOT`;
- `SILICIUM_SEED_PEERS`;
- `SILICIUM_MESH_KEY`;
- `SILICIUM_DASHBOARD_URL`.

Pour un deploiement reel, ces valeurs devront etre fournies par l'environnement de production et non par les valeurs par defaut de developpement.
