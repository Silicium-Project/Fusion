# Développement et commandes communes

## Prérequis

Les versions sont déclarées dans `tools/config/toolchains.json`. L'outillage
portable utilise Node.js, Git et, pour GitHub, `gh auth login`. Les applications
conservent leurs lockfiles npm et le programme Anchor son lockfile Yarn.

`./dev doctor --profile <profil>` vérifie la présence des outils sans installer
ni modifier le poste. Les profils sont `tooling`, `web`, `api`, `node`,
`network`, `solana`, `delivery` et `all`.

```sh
./dev doctor --profile tooling
./dev capabilities --json
./dev ci plan --base origin/main --head HEAD --output .artifacts/plan.json
./dev test --suite tooling --plan .artifacts/plan.json
```

Sous Windows : `.\dev.ps1 doctor --profile node`. Un terminal Git Bash est
nécessaire pour les scénarios shell ; les tests natifs utilisent Windows.
Les rapports et sorties temporaires sont dans `.artifacts`, ignoré par Git.

## Suites

La liste exacte est donnée par `dev capabilities`. Les suites incluent :
`tooling`, `docs`, `api`, `web`, `node-ui`, `node-native`, `node-windows`,
`network`, `network-integration`, `solana` et `infrastructure`.

Les commandes sont définies une fois dans `tools/config/lanes.json`. La CI
appelle `dev test --suite ...` ; un changement de dépendance ou de contrat
qualifie aussi les consommateurs. Une surface inconnue impose la matrice.
`dev check --changed --base origin/main` exécute l'ensemble des suites choisies.

## Applications

```sh
cd apps/web
npm ci
npm run dev
```

L'API se développe dans `apps/api` avec Go et une configuration locale issue
des exemples ; le réseau se développe dans `network` avec Cargo. Le desktop
se développe dans `apps/node` après installation des prérequis Tauri de l'OS.
Les commandes `dev build --component ...` construisent sans publier.

Les sorties de `doctor` et des tests doivent distinguer un prérequis absent,
un échec et une validation réussie. Les tests blockchain de CI utilisent
localnet et des clés jetables ; Devnet est une opération explicite distincte.

## GitHub

`dev ci inspect --run ID` lit les preuves d'une exécution. `dev issue start URL`
prépare une transition du Project ; `--apply` la réalise après contrôle du WIP.
`dev release plan` prépare un candidat ; `dev deploy request` prépare ou lance
un workflow GitHub. Les étapes de production et d'acceptation sont humaines.

`dev ops diagnose --environment dev --json` prépare les observations CPU,
disque, conteneurs et RPC. `--apply` demande le workflow protégé : voir
[les diagnostics](../operations/diagnostics.md). Le [miroir Epitech](../operations/epitech-mirror.md)
est une automatisation GitHub distincte, indépendante de la livraison.
