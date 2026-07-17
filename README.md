# Silicium

Silicium regroupe le reseau de calcul distribue, le layer Solana Devnet, le dashboard d'observation et le site client.

Les composants Network, BackEnd et FrontEnd sont suivis comme submodules Git pour garder leur cycle de vie independant tout en restant composes par Fusion.

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
- le backend du site sur `http://localhost:8080`;
- le frontend du site sur `http://localhost:3000/dashboard`.

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
