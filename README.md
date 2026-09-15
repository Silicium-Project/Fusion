# Silicium

Silicium regroupe le reseau de calcul distribue, le layer Solana Devnet, le dashboard d'observation et le site client.

Les composants Network, BackEnd et FrontEnd sont suivis comme submodules Git pour garder leur cycle de vie independant tout en restant composes par Fusion.

Le plan d'attaque fige, le tri actif/transition/vestige et le topologie CI/CD
canonique sont documentes dans:

- [docs/repo-attack-plan-and-triage.md](docs/repo-attack-plan-and-triage.md)
- [docs/ci-cd-topology.md](docs/ci-cd-topology.md)

The visible GitHub path is now simple: `Build`, `Test`, then `Deploy`. Linux
validation and deployment remain on the VPS runners, while the Windows desktop
installer is built on GitHub-hosted Windows capacity. `Build` and `Test` remain
reusable gates for pull requests and manual runs; `Deploy` carries the complete
mainline chain before publication on the VPS.
Le miroir externe vers le repo Epitech reste volontaire et explicite via
`mirror-epitech.yml`, declenche apres un `Deploy` reussi, sans faire partie du
chemin critique de livraison.

Les releases suivent deux canaux explicites décrits dans
[`deploy/release/channels.json`](deploy/release/channels.json) : `dev` pour les
pushs de développement et `prod` pour `main`/les tags `v*`. Le front, le back,
les nœuds et le réseau publient leur canal, version et build ; les pairs réseau
ne mélangent pas les canaux. Une promotion vers la production passe par une
merge revue de `dev` vers `main`.

Fusion conserve des SHA exacts afin que chaque build, rollback et deploiement soit
reproductible. Le workflow `Sync submodule gitlinks` examine toutes les cinq
minutes la composition `prod` sur `main`; il peut aussi synchroniser explicitement
la composition `dev` vers la branche `dev`. Dans les deux cas, il selectionne pour
chaque submodule le dernier commit dont les workflows du canal sont tous verts,
puis publie cette composition exacte sur la branche correspondante. Le push
`main` declenche le pipeline VPS de production; le workflow manuel
`deploy-dev-vps.yml` deploye explicitement la composition `dev` sous
`/opt/silicium-dev` sans toucher a la production.
`submodule-ci-gate` reutilise le meme resoluteur et refuse une composition sans
candidat vert. Si le head courant est encore rouge ou en attente, Fusion reste
sur le dernier commit vert au lieu d'introduire une revision non qualifiee.
Il ne faut pas remplacer ce mecanisme par un `git submodule update --remote`
pendant le deploiement: le contenu deploye ne correspondrait alors plus au
commit Fusion audite.

Le canal `dev` est prive par WireGuard sur le VPS (`10.77.0.1:8443`) ; la
production reste l'unique ingress web publique. Voir [deploy/README.md](deploy/README.md)
pour creer ou revoquer les pairs de l'equipe.

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

- un noeud de calcul et un noeud de verification via le launcher Network;
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

- `DATABASE_URL`, utilisee lorsque `DATABASE_DRIVER=postgres`;
- `DATABASE_DRIVER`, `sqlite` en local par defaut, `postgres` pour une vraie DB;
- `SQLITE_PATH`, avec `.silicium\site\silicium.db` par defaut;
- `JWT_SECRET_KEY`, avec une valeur locale de developpement si absente;
- `SILICIUM_NETWORK_ROOT`;
- `SILICIUM_SEED_PEERS`;
- `SILICIUM_MESH_KEY`;
- `SILICIUM_DASHBOARD_URL`.

Pour un deploiement reel, ces valeurs devront etre fournies par l'environnement de production et non par les valeurs par defaut de developpement.
