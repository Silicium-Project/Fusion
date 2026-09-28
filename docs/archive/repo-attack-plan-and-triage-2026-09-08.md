# Plan d'attaque figé et tri du repo

Date de gel: 2026-09-08

Ce document fige le périmètre de travail actuel de `Fusion` et sépare le dépôt en trois classes:

- `actif`: code et infra qui servent le produit maintenant;
- `transition`: code encore utile mais destiné a etre remplace ou simplifie;
- `vestige`: artefacts, caches, doublons ou references documentaires obsoletes.

Le but est d'eviter de re-travailler tout le repo a chaque iteration et de ne pas confondre un composant en production avec un reliquat historique.

## 1. Plan d'attaque fige

### Axe A - Runtime reseau et P2P

Objectif:

- stabiliser le noeud P2P;
- finir la migration vers le coeur Rust `p2p_node`;
- garder la compatibilite seulement tant que les issues de remplacement ne sont pas closes.

Composants actifs:

- `Network/networked/p2p_node`
- `Network/infra/bootstrap`
- `Network/docs/p2p-direct-transport-contract.md`
- `Network/tools/network_node.py` tant que le launcher Python reste l'orchestrateur de reference

Composants en transition:

- `Network/tools/network_node.py`
- `Network/bin/raytracer/raytracer`
- `Network/bin/raytracer/raytracer.cmd`
- tous les chemins de fallback encore relies a Python ou a des wrappers legacy

Critere de fin:

- le lancement du noeud ne depend plus de la glue Python de production;
- les fallbacks legacy ne servent plus qu'en secours temporaire ou sont supprimes;
- les tests E2E couvrent multi-workers, RPC, web submit et VPS reel.

### Axe B - Solana layer et dashboard

Objectif:

- garder le layer Solana comme surface on-chain stable;
- conserver le dashboard Devnet et les tests de smoke;
- ne pas casser les flows de consultation tant que l'indexation n'est pas remplacee.

Composants actifs:

- `Network/solana-layer`
- `Network/silicium-layer-dashboard`
- `deploy/linux/build-site.sh`
- `deploy/linux/install-services.sh`
- `deploy/compose/deploy.sh`

Composants en transition:

- toute documentation qui parle encore d'un unzip manuel du dashboard ou d'un ancien emplacement
- les scripts qui contiennent des chemins de compatibilite pour du runtime deja empaquete ailleurs

Critere de fin:

- le dashboard est installe et lance de maniere reproductible depuis les scripts de repo;
- l'IDL et les tests Anchor restent alignes avec les workflows CI;
- les docs ne mentionnent plus de flux de distribution obsoletes.

### Axe C - Produit site, backend et VPS

Objectif:

- garder le site client, le backend et le deploiement VPS comme voie de livraison principale;
- faire converger CI, deploy et post-deploy checks sur le meme chemin d'execution.

Composants actifs:

- `BackEnd`
- `FrontEnd`
- `deploy`
- `.github/workflows/deploy-vps.yml`
- `.github/workflows/sync-submodules.yml`
- `.github/workflows/submodule-ci-gate.yml`
- `.github/workflows/mirror-epitech.yml`
- `docs/ci-cd-topology.md`

Composants en transition:

- tout ce qui suppose encore des secrets ou chemins de publication temporaires;
- les scripts qui compensent des etats de migration du VPS.

Critere de fin:

- le deploiement VPS produit une stack stable;
- Fusion echoue explicitement si un seul submodule `main` a une CI rouge, en
  attente ou incomplete;
- les tests de bout en bout couvrent plusieurs workers et plusieurs tasks en parallele;
- les builds longs sont budgetes explicitement dans CI.

## 2. Tri du repo

### A garder

- `Network/networked/p2p_node`
- `Network/solana-layer`
- `Network/silicium-layer-dashboard`
- `Network/tools`
- `Network/docs`
- `BackEnd`
- `FrontEnd`
- `apps/silicium-node`
- `deploy`
- `.github/workflows`
- `README.md`

### A garder mais a considerer comme transitoire

- `Network/tools/network_node.py`
- `Network/bin/raytracer/*`
- `Network/workloads/raytracer/*` quand ils servent encore de harness ou de fallback
- `apps/silicium-node/src-tauri/src/lib.rs` pour la gestion du runtime et des mises a jour tant que le packaging n'est pas completement simplifie

### A considerer comme vestige ou bruit

- caches Python: `.pytest_cache/`, `__pycache__/`
- caches Node: `node_modules/`, `.nuxt/`, `.output/`
- artefacts de build: `dist/`, `target/`, `apps/**/src-tauri/target/`, `Network/solana-layer/target/`, `Network/solana-layer/idl/`
- logs locaux et fichiers d'execution: `*.log`, `deploy-job-*.log`, `desktop-job-*.log`, `node8-build.log`, `timeout-fix-live-*.log`
- metadata locale de copie de submodule: `BackEnd/.git`, `FrontEnd/.git`, `Network/.git`
- caches internes locaux: `.agents/`, `.silicium/`, `Network/.silicium/`

## 3. Nettoyage applique

Le tri de septembre 2026 a retire les anciennes chaines C++/Qt, les fixtures
PE, les generateurs de couverture, les stacks Docker de demonstration et les
inventaires de securite correspondants du repo Network. Les anciens services
systemd du site et les doublons de packaging a la racine de Fusion ont aussi
ete retires au profit de Compose et des workflows canoniques.

Les seuls vestiges acceptes sont les scripts de migration et de compatibilite
qui servent encore a remettre un VPS existant dans le chemin courant. Les logs,
caches et sorties de build ne doivent jamais etre utilises comme source de
verite.

## 4. Regle de gouvernance

Pour les prochaines itérations:

- ne pas ajouter de nouveau fallback Python si un chemin Rust ou binaire existe deja;
- ne pas considerer un benchmark valide si un seul worker a traite toute la charge;
- ne pas faire evoluer les scripts de deploy sans verifier le trajet local + VPS;
- ne pas laisser Fusion avancer si un submodule `main` est rouge, meme si les
  autres sont verts;
- ne pas redeployer une architecture CI/CD tant que le chemin VPS-first n'est
  pas documente dans `docs/ci-cd-topology.md`;
- ne pas fusionner une migration tant que le chemin de claim/dispatch/reconciliation n'est pas teste sur le vrai flux.

## 5. Ordre de travail recommande

1. Finir le remplacement de la glue Python par le coeur Rust quand le bloc `p2p_node` est a niveau.
2. Stabiliser les tests E2E multi-workers, web et RPC avec budget de build explicite.
3. Verrouiller le pipeline VPS unique: `sync-submodules` publie la composition
   sur les derniers commits verts, `deploy-vps` porte build, test et deploy,
   et les workflows `build` / `test` restent des gates reutilisables pour les
   PR.
4. Nettoyer la documentation qui pointe vers des chemins historiques.
5. Purger ou ignorer strictement les caches et artefacts locaux.
6. Ne garder dans le repo que les composants qui servent un flux deployable ou une transition encore assumee.
