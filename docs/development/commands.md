# Développement et commandes communes

## Sources et scopes

`./dev workspace status --json` vérifie pins et checkouts sans réseau.
`./dev workspace init --component web` prépare un aperçu ; `--apply` récupère
le commit exact avec les droits Git locaux. `workspace verify --materialized`
exige les cinq sources propres. `workspace pin --component web --revision SHA
--apply` prépare ensemble gitlink et lock, sans écraser de travail divergent.

Le plan accepte `--scope public` pour Workbench, `--scope component:web` pour
une qualification native et `--scope integration` pour tous les composants.
Le scope `local` conserve le routage par changements. Les suites différées
restent obligatoires avant livraison ; une réussite publique ne les remplace pas.
Voir [les frontières et limites](../architecture/multi-repo.md).

Dans un clone natif :

```sh
export SILICIUM_WORKBENCH=/chemin/vers/Workbench
./dev doctor
./dev prepare                   # aperçu
./dev test --suite web          # composition temporaire, suite commune
```

Le checkout Workbench et le composant doivent être propres et committés. Le
rapport conserve leurs deux SHA. `--destination` choisit un dossier inexistant ;
aucun dossier existant n’est remplacé. Les compositions temporaires ne sont pas
poussées. Pour développer dans les sous-modules, créer une branche native avant
les modifications ; `workspace init` refusera ensuite d’écraser cette divergence.

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

Le [guide de qualité](quality.md) décrit le formatage, les analyses et les
versions verrouillées. `dev format --write` reformate les sources ; sans cette
option, la commande les vérifie. Exécuter `npm ci --prefix tools/quality
--ignore-scripts --no-audit --no-fund` une première fois pour ces outils.

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

`dev ci inspect --run ID` lit les preuves Workbench ; ajouter
`--repository Silicium-Project/Integration` (ou le dépôt natif déclaré) pour
une exécution privée avec les droits du compte GitHub courant. `dev issue start URL`
prépare une transition du Project ; `--apply` la réalise après contrôle du WIP.
`dev release plan` prépare un candidat ; `dev deploy request` prépare ou lance
un workflow GitHub. Les étapes de production et d'acceptation sont humaines.

`dev ci metrics --limit 20 --json` (schéma 2) mesure les durées médianes et p95,
le retour des contrôles rapides, l'attente avant démarrage des workflows, l'attente
des jobs, les échecs et les observations de cache disponibles. La commande lit
les métadonnées GitHub et télécharge les petits rapports dans un répertoire
temporaire supprimé après lecture. Ces téléchargements sont plafonnés à 16 Mio
par run et 64 Mio au total ; les runs les plus récents sont traités en premier.
La sortie indique le budget réservé et le nombre de runs ignorés si le plafond
est atteint ; un lot supérieur à 16 Mio par run est ignoré et signalé. Elle ne
relance aucun job. Les échantillons manquants et les caches désactivés restent
distincts des valeurs nulles ou des échecs de cache. Les
artefacts Workbench sont paginés jusqu'à 10 000 entrées ;
si le relevé reste incomplet ou change pendant la pagination, `bytes` vaut `null`
et `bytes_observed` ne donne que le sous-total effectivement lu.

`workflow_start_wait` part de la création du run jusqu'à `run_started_at` : il
mesure l'attente avant que les jobs existent. `job_queue_and_matrix_wait` part de
`job.created_at` jusqu'à la première étape exécutée : il inclut ensuite la file,
la limitation de matrice et le provisionnement du runner. Ces deux mesures ne
doivent pas être confondues ; une date absente reste une observation indisponible.

`dev ci authorize-private --head SHA --minutes 180` prépare une fenêtre de
qualification privée du commit exact. `--apply` exige les droits administratifs,
un budget Actions à zéro avec arrêt des dépassements, et suspend les anciens
workflows avant d'autoriser cette seule qualification. Voir
[la procédure](../operations/bootstrap.md#qualification-ponctuelle-tout-en-restant-privé).

`dev ops diagnose --environment dev --json` prépare les observations CPU,
disque, conteneurs et RPC. `--apply` demande le workflow protégé : voir
[les diagnostics](../operations/diagnostics.md). Le [miroir Epitech](../operations/epitech-mirror.md)
est une automatisation GitHub distincte, indépendante de la livraison.
