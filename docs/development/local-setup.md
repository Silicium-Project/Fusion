# Environnement local de développement

## Installation (Windows)

Depuis la racine du repository:

```powershell
git clone --recurse-submodules https://github.com/Silicium-Project/Fusion.git
.\install-silicium-windows.cmd -InstallSystemDeps
```

Si le repository a ete clone sans recurse-submodules, lancez d'abord:

```powershell
git submodule update --init --recursive
```

Ce script verifie/installe les outils systeme principaux, puis installe les dependances npm du layer Solana et du site.

## Raytracer natif

Les nœuds de calcul ont besoin du binaire `silicium-raytracer` :

```powershell
cargo build --release --manifest-path Network\crates\raytracer\Cargo.toml
```

`install-silicium-windows.cmd` le trouve ensuite automatiquement
(`Network\crates\raytracer\target\release\silicium-raytracer.exe`).

## Lancement local en une commande

Depuis la racine du repository:

```powershell
.\start-silicium-local.cmd
```

Le lancement local suppose que les submodules sont initialises.

Le script demarre:

- un noeud de calcul et un noeud de verification via le launcher Network;
- une base SQLite locale dans `.silicium\site\silicium.db` par defaut;
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

- `DATABASE_URL`, utilisee lorsque `DATABASE_DRIVER=postgres`;
- `DATABASE_DRIVER`, `sqlite` en local par defaut, `postgres` pour une vraie DB;
- `SQLITE_PATH`, avec `.silicium\site\silicium.db` par defaut;
- `JWT_SECRET_KEY`, avec une valeur locale de developpement si absente;
- `SILICIUM_NETWORK_ROOT`;
- `SILICIUM_SEED_PEERS`;
- `SILICIUM_MESH_KEY`.

Pour un deploiement reel, ces valeurs devront etre fournies par l'environnement de production et non par les valeurs par defaut de developpement.
