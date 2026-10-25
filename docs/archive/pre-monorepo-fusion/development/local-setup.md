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

## Binaires du réseau

Le réseau local utilise les binaires Rust du dépôt Network (`p2p_node`,
`compute_daemon`, `silicium-raytracer`). `start-silicium-local.cmd` les compile
s'ils manquent ; pour les construire à l'avance :

```powershell
cargo build --release --locked --manifest-path Network\Cargo.toml -p p2p_node -p compute_daemon -p silicium-raytracer
```

## Lancement local en une commande

Depuis la racine du repository:

```powershell
.\start-silicium-local.cmd
```

Le lancement local suppose que les submodules sont initialises.

Le script demarre:

- un orchestrateur local (`p2p_node`, API sur le port 46100) et un worker
  (`compute_daemon` + `p2p_node`) qui lui fait confiance par son adresse
  d'amorçage épinglée, comme l'application de bureau (donnees dans
  `.silicium\local-network`);
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
- `SILICIUM_NODE_API_URL` et `SILICIUM_NODE_CONTROL_TOKEN`, l'API de
  l'orchestrateur local (`p2p_node`) que `start-silicium-local` demarre avec un
  worker;
- `SILICIUM_ORCHESTRATOR_EXPORT_DIR` et `SILICIUM_WORKLOAD_STORAGE_DIR`, les
  fichiers ecrits par cet orchestrateur.

Pour un deploiement reel, ces valeurs devront etre fournies par l'environnement de production et non par les valeurs par defaut de developpement.
