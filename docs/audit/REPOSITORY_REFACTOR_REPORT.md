# Rapport d’audit et de refonte des dépôts Silicium

Date de référence : 29 juillet 2026  
Branche d’audit : `audit/full-repo-2026-07-29`  
Composition Fusion auditée :

- Fusion : `97d188fc95b7f73f37b7edd0af418a0e259d871e` ;
- Network : gitlink de la composition Fusion, après intégration du filtrage des tâches terminales et du contrôle RPC ;
- BackEnd : `d87f3d564304505eeb1de81da56eb5fc3230e501` dans la composition Fusion ;
- FrontEnd : `c5c314fa0e6e2c2791b369c2e92ce3f3c346f03c` dans la composition Fusion.

> Le dépôt `Fusion` est la source de vérité de la composition. Les branches `main` individuelles de BackEnd et FrontEnd peuvent être plus avancées que les gitlinks déployables ; l’audit d’exécution utilise donc les SHA épinglés par Fusion, pas arbitrairement les derniers commits des sous-dépôts.

## 1. Résumé exécutif

Silicium n’est pas un « énorme monorepo ». C’est une composition de quatre dépôts relativement distincts, mais dont les frontières de production sont aujourd’hui poreuses :

- Fusion orchestre les versions, le déploiement VPS et les applications desktop ;
- Network contient à la fois runtime de production, protocoles, CLI, API MCP/RPC, workloads, transports P2P, dashboard Devnet, C/C++, Rust, Solana, prototypes, démonstrations et documentation ;
- BackEnd expose le produit web, persiste les jobs et lance encore des chemins Python de Network ;
- FrontEnd regroupe l’expérience utilisateur du site Nuxt.

Le risque principal n’est pas le nombre de fichiers, mais l’absence de **surface de production explicitement déclarée**. L’image orchestrateur copie actuellement tout le dépôt Network et le packaging desktop copie de larges répertoires. Un fichier peut donc être utilisé indirectement par Docker, PowerShell, subprocess, une variable d’environnement ou un fallback, même sans import statique.

Les priorités sont :

1. **P0 — durcir la configuration de production** : supprimer les secrets de démonstration, les endpoints/IP codés en dur et le CORS permissif ;
2. **P0 — figer les contrats observables** avant la migration native de Network#247 et le task book de Network#257 ;
3. **P1 — rendre les contrôles CI obligatoires et reproductibles** ;
4. **P1 — construire depuis des manifests de production minimaux** plutôt que copier des dépôts entiers ;
5. **P1 — découpler les monolithes**, particulièrement `tools/network_node.py`, `silicium`, `tools/mcp_server.py`, `networkController.go` et `pages/dashboard.vue` ;
6. **P2 — archiver uniquement après preuve de non-utilisation**, jamais selon le nom du dossier.

## 2. Méthodologie et niveaux de preuve

L’audit distingue trois niveaux de preuve.

### 2.1 Lecture manuelle ciblée

Les chemins critiques suivants ont été examinés directement :

- composition Git/submodules et workflows de synchronisation ;
- Compose de production, Dockerfiles, Nginx et variables d’environnement ;
- packaging Windows/Linux de Silicium Node ;
- points d’entrée CLI, nœud, MCP, RPC, réseau, worker et raytracer ;
- contrôleurs et routes BackEnd ;
- page dashboard et configuration FrontEnd ;
- workflows CI des quatre surfaces ;
- issues et epics d’architecture ouverts.

### 2.2 Inventaire exhaustif automatisé

Les workflows d’audit ajoutés dans cette branche utilisent `git ls-files` dans Fusion et chacun des trois submodules. Chaque fichier régulier suivi est :

- ouvert ;
- lu en binaire ;
- haché en SHA-256 ;
- classé par dépôt, extension, taille, type texte/binaire et cycle de vie candidat ;
- décodé en UTF-8 lorsqu’il est textuel ;
- analysé pour les lignes longues, espaces finaux, encodages, duplications exactes et motifs de sécurité/maintenabilité.

Les résultats sont écrits sous :

- `docs/audit/generated-fast/` pour l’inventaire et les contrôles principaux ;
- `docs/audit/generated/` pour la passe profonde, les builds optionnels et les logs par commande.

### 2.3 Exécution reproductible

Chaque commande est exécutée indépendamment avec timeout et journal dédié. Une panne précoce ne masque donc pas les contrôles suivants. Les surfaces comprennent notamment :

- Fusion : submodules, Compose, application Tauri/Vue et tests Rust ;
- BackEnd : `gofmt`, `go vet`, `go test`, build et image Docker ;
- FrontEnd : installation, Vitest, build Nuxt, Playwright et image Docker ;
- Network : compilation Python, UTF-8, i18n, règles de style, manifests, corpus golden, pytest, raytracer Rust, C/C++ worker/executor, viewer Qt, dashboard React, Solana et smoke tests ;
- construction de la stack de production.

Les journaux sont des preuves d’exécution, pas une promesse implicite de réussite. Les échecs spécifiques à la plateforme ou aux dépendances restent des remédiations à traiter.

## 3. Architecture réellement déployée

### 3.1 Serveur/VPS

`deploy/compose/docker-compose.yml` définit actuellement :

- PostgreSQL ;
- coturn ;
- BackEnd Go ;
- FrontEnd Nuxt ;
- dashboard Devnet construit depuis `Network/silicium-layer-dashboard` ;
- orchestrateur/nœud Python construit depuis Network ;
- experiment API/MCP-RPC ;
- proxy Nginx.

Le backend monte `/opt/silicium/Network` et `/var/lib/silicium`. L’orchestrateur exécute `python /opt/silicium/Network/silicium node start`. L’experiment API exécute directement `tools/mcp_server.py`. La production reste donc dépendante du runtime Python Network et de ses contrats de fichiers.

### 3.2 Application desktop

Le packaging Silicium Node :

- compile le raytracer Rust natif ;
- copie le CLI `silicium` ;
- copie `tools/`, `workloads/`, `bin/` et `networked/` ;
- embarque un runtime Python ;
- installe les dépendances P2P ;
- embarque/répare OpenSSL sous Windows.

Ce packaging est une source d’usage au même titre que les imports. Toute décision d’archive doit analyser ces scripts.

### 3.3 Site

Le FrontEnd appelle BackEnd pour les jobs et la vue RPC. BackEnd lit également des fichiers d’export produits par Network. La frontière n’est pas une API stable isolée : c’est un mélange d’HTTP, de fichiers JSON, de commandes et de callbacks.

## 4. Constat transversal

## 4.1 P0 — secrets et configuration de production

Le Compose de production contient des fallbacks de type `demo-mesh` pour la clé mesh et le mot de passe TURN, ainsi que des IP/domaines publics codés en dur. Les fichiers `.example.env` contiennent à juste titre des placeholders, mais ces placeholders ne doivent jamais devenir des valeurs de repli de production.

BackEnd utilise `CORS_ALLOWED_ORIGINS=*` par défaut avec `AllowCredentials=true`. Une production mal configurée peut donc démarrer dans un mode dangereux ou incohérent.

Remédiation :

- mode `development` explicite et mode `production` strict ;
- `${VAR:?required}` dans Compose pour tous les secrets ;
- validation au démarrage ;
- rotation des valeurs ayant pu être utilisées hors local ;
- aucune valeur secrète dans les logs d’audit ;
- test négatif prouvant que la production refuse de démarrer avec des valeurs de démonstration.

## 4.2 P0 — contradiction entre runtime courant et architecture cible

Network#257 interdit toute autorité de scheduler central. Pourtant le runtime actuel :

- sonde des seeds/discovery peers ;
- appelle `/tasks/claim` ;
- utilise les termes `scheduler-http`, `route=central` et `no_scheduler_target` ;
- stocke encore un état de file dans les exports du pair interrogé.

Ce chemin est acceptable uniquement comme **adaptateur de migration legacy**, pas comme fondation à renforcer. La migration native Network#247 doit implémenter le task book répliqué avant de supprimer les adaptateurs Python.

## 4.3 P1 — surface de production non bornée

L’image orchestrateur fait un `COPY Network/ /opt/silicium/Network/`. Le contexte de production peut donc contenir : tests, docs, anciens prototypes, viewer, fixtures, caches oubliés ou scripts sans rapport avec le service.

Le desktop copie également des répertoires complets. Cela augmente :

- taille et temps de build ;
- surface d’attaque ;
- difficulté de licence/SBOM ;
- risque de fuite de fichiers ;
- contexte fourni aux agents.

La cible est un manifeste d’allowlist par artefact, avec échec si un fichier inattendu entre dans le bundle.

## 4.4 P1 — monolithes et duplication de configuration

### `Network/tools/network_node.py`

Environ 6 740 lignes. Il agrège :

- parsing de configuration ;
- identité Ed25519 ;
- sérialisation et stockage JSON ;
- queues, retries et recovery ;
- réputation ;
- HTTP, gossip, ICE, STUN, TURN et relay ;
- sélection des pairs ;
- task control ;
- exécution des workloads ;
- receipts, télémétrie et CLI.

### `Network/silicium`

Environ 4 730 lignes. Il cumule CLI, shell, Docker, tests, nettoyage, ledger, MCP, node, workload, TUI et configuration. Il duplique les arguments et defaults du nœud.

### `Network/tools/mcp_server.py`

Environ 1 775 lignes. Il contient ressources, politiques, stockage de tâches, snapshots, observabilité, JSON-RPC, HTTP et bootstrap. Les snapshots (#145) sont livrés ; TLS, limites de concurrence et backpressure restent à isoler.

Conséquence : une petite modification charge plusieurs domaines et multiplie les risques de régression. Pour l’agent, ce sont des fichiers à très fort coût de contexte.

La stratégie ne doit pas être une réécriture Python totale si Python doit disparaître. Il faut :

1. figer les contrats ;
2. extraire seulement les adaptateurs nécessaires ;
3. migrer par frontières vers Rust/C++ ;
4. comparer les anciens/nouveaux états ;
5. supprimer les wrappers en dernier.

## 4.5 P1 — CI incomplète ou conditionnelle

Le workflow principal Network protège certains contrôles par `SILICIUM_ENABLE_HOSTED_CI == 1`. Un contrôle requis ne doit pas dépendre d’une variable opt-in silencieuse.

Des contrôles personnalisés existent et sont utiles, mais il manque une politique homogène :

- aucun `.editorconfig` commun ;
- Python sans Ruff/Pyright standard dans les dépendances visibles ;
- applications TypeScript sans scripts ESLint/Prettier cohérents ;
- rapports de couverture commités par workflow sur `main` ;
- contrôles Go non présents dans la composition Fusion ;
- Shell/PowerShell/Actions non couverts uniformément.

La transition doit utiliser un ratchet : contrôler d’abord les lignes/fichiers modifiés, enregistrer la dette existante, puis la réduire. Une PR globale de formatage ne doit pas contenir de changement comportemental.

## 4.6 P2 — artefacts générés et encodage

Network publie déjà la couverture via GitHub Pages, mais un second job commit encore les HTML/JSON/SVG dans le dépôt. Ces fichiers :

- gonflent l’historique ;
- polluent les recherches ;
- créent des diffs automatisés ;
- consomment inutilement le contexte des agents.

Le README contient aussi des marqueurs de mojibake visibles dans les badges de couverture. Une validation UTF-8 existe ; elle doit s’accompagner d’une correction de l’historique textuel pertinent.

## 5. Audit par dépôt

## 5.1 Fusion

### Forces

- composition reproductible par gitlinks exacts ;
- synchronisation des submodules via GitHub App ;
- pipeline de release et déploiement déjà largement automatisé ;
- application desktop avec tests Vue/Rust ;
- manifests de mise à jour signés et mécanismes de rollback en cours de maturation.

### Faiblesses

- Compose très lié à une machine/IP spécifique ;
- secrets de démonstration comme fallbacks ;
- broad Docker contexts ;
- scripts PowerShell/Bash volumineux et multi-responsabilités ;
- `.gitignore` contenant des règles historiques de l’époque où les sous-dépôts étaient importés, par exemple metadata `.git` et package-lock de submodule ;
- duplication des responsabilités entre workflows, scripts de packaging et services systemd/Compose ;
- absence de manifeste de composants et de production.

### Décision

Fusion doit devenir le dépôt de **composition et de preuve**, pas un second lieu d’implémentation métier. Les tickets métier restent dans leur dépôt propriétaire ; Fusion suit intégration, gitlinks, E2E, release et déploiement.

## 5.2 Network

### Forces

- large corpus de tests et de fixtures ;
- contrôles UTF-8, i18n, conventions C++ et budgets de performance ;
- identities/signatures, télémétrie et recovery déjà développés ;
- transports P2P et tests ciblés ;
- raytracer Rust natif ;
- roadmap native (#247–#254) et protocolaire (#257) explicites.

### Faiblesses

- plusieurs générations de runtime cohabitent ;
- monolithes Python ;
- vocabulaire `scheduler`, `orchestrator`, `emitter`, `world` incohérent ;
- code produit, expérimental, historique et démonstration dans le même espace ;
- CI conditionnelle et coverage générée dans Git ;
- viewer Qt encore actif dans l’historique récent, donc non archivable sans décision produit ;
- `experimental/worker` reste référencé comme binaire par défaut ;
- `worker/` et `executor/` sont toujours construits/testés ;
- large surface de fichiers copiée dans les artefacts.

### Décision

Ne pas lancer un « grand nettoyage » avant les contrats de caractérisation. L’ordre est : fixtures/contrats, surface de production, migration native, puis archives.

## 5.3 BackEnd

### Forces

- stack Go simple ;
- routes authentifiées ;
- jobs, annulation, billing et orchestration déjà couverts par plusieurs PRs ciblées ;
- Docker multi-stage ;
- séparation générale `cmd/internal`.

### Faiblesses

- `internal/handler/networkController.go` mélange lecture de fichiers, parsing non typé, tri, agrégation, versions et HTTP ;
- chemins `/var/lib/silicium/...` codés dans le handler ;
- nombreuses expressions compactées sur une seule ligne ;
- réponse réseau fondée sur `map[string]any` ;
- pas d’issue ouverte malgré une dette identifiable ;
- `cmd/main.go` utilise `http.ListenAndServe` directement, sans timeouts ni graceful shutdown ;
- CORS permissif par défaut ;
- image finale `alpine:latest` non immuable ;
- le runtime Go embarque Python/OpenSSL pour les jobs, ce qui confirme un couplage transitoire à documenter.

### Décision

Créer une couche `networkregistry` typée avec repository/service/handler, injecter la configuration, puis durcir le cycle de vie HTTP. Cette refonte peut être réalisée indépendamment de la migration native, à condition de conserver le contrat JSON.

## 5.4 FrontEnd

### Forces

- Nuxt/Vue moderne ;
- Vitest et Playwright ;
- intégration jobs, annulation, résultats et vue réseau ;
- build de production CI existant.

### Faiblesses

- `pages/dashboard.vue` concentre navigation, état, API, formulaire, Solana et graphiques ;
- types `any` aux frontières ;
- type de réponse réseau incohérent avec la propriété `workloads` consommée ;
- graphiques de devices codés en dur et option `userGrowthOptions` inutilisée ;
- liens placeholder ;
- console logging comme stratégie principale d’erreur ;
- absence de lint/format standard dans les scripts ;
- pas d’issue ouverte pour cette dette.

### Décision

Extraire composables, types et composants, sans redesign simultané. D’abord fiabiliser les contrats, ensuite l’UX.

## 6. Classification de cycle de vie proposée

| Zone | Statut initial | Action |
|---|---|---|
| `Fusion/deploy/**` | production | conserver, externaliser config, tester |
| `Fusion/apps/silicium-node/**` | production desktop | conserver, réduire runtime bundle |
| `Network/tools/network_node.py` | production legacy | geler, caractériser, remplacer via #247/#257 |
| `Network/tools/mcp_server.py` | production legacy | geler, fermer scopes livrés, migrer via #249 |
| `Network/networked/**` | production legacy/adapter | conserver pendant dual-write |
| `Network/workloads/raytracer/**` | production | conserver, séparer host et plugin |
| `Network/proto/**` | contrat production | conserver, versionner/golden fixtures |
| `Network/silicium-layer-dashboard/**` | production dashboard | conserver |
| `Network/catalog/workloads/**` | contrat métier | conserver |
| `Network/worker/**` | actif/CI | ne pas archiver |
| `Network/executor/**` | actif/CI | ne pas archiver |
| `Network/experimental/worker/**` | référencé legacy | archivage bloqué tant que default existe |
| anciens splitter/executor historiques | legacy-candidate | prouver références puis extraire/retirer |
| `Network/viewer/**` | supported-dev ou legacy-candidate | décision produit + preuve build/package |
| `Network/demo/**` | demo/test dependency | inventorier les consommateurs avant retrait |
| `docs/coverage/**` généré | generated | retirer de `main`, conserver Actions/Pages |
| BackEnd `internal/**` | production | typer et découpler |
| FrontEnd `pages/components/**` | production | modulariser sans casser l’API |

## 7. Règle d’archivage

Un candidat n’est archivable que si les six preuves suivantes existent :

1. aucun import ou chargement dynamique ;
2. aucune référence Docker, CI, packaging, script ou documentation opérable ;
3. aucune exécution observée dans les scénarios de production ;
4. remplacement identifié et tests verts sans le candidat ;
5. owner/ADR validant la fin de support ;
6. récupération garantie par tag, branche d’archive ou dépôt historique extrait.

Ne pas déplacer le code dans `archive/` sur `main` : il continuerait à être indexé, testé accidentellement et envoyé aux agents.

## 8. Décisions de backlog

### Candidats à clôture démontrés

- Fusion#67 : renommage `NetworkedOrchestrator` vers `LocalNetworkEmitter` livré et intégré ;
- Network#145 : snapshots MCP, rétention, export/import et tests livrés ;
- Network#199, #200, #201 : titres et corps marqués `Done`, avec preuves annoncées.

### Epics à conserver

- Fusion#74 : umbrella produit/cross-repo ;
- Network#247 : migration native et retrait Python ;
- Network#257 : task book P2P et absence d’autorité centrale ;
- Network#280 : workload Blender, dépendant de #257.

### Rescoping

- Network#122 : politique locale de concurrence/fairness, pas scheduler réseau ;
- Network#251 : host local et état dérivé, subordonné à #257 ;
- Fusion#84 : tracker d’intégration uniquement ;
- Network#209 : fondation milestone générique ;
- Network#284/#285 : spécialisations Blender ;
- Network#75 : umbrella viewer ownership ; #174 reste un patch atomique ;
- Network#205 : réévaluer contre le runtime actuel et fermer le scope livré avant d’ouvrir les gaps restants.

Le plan machine-readable est dans `docs/audit/ISSUE_PLAN.json`.

## 9. Architecture cible de refonte

### 9.1 Contrats d’abord

Créer un registre de contrats versionnés :

- événements task book ;
- protobuf RPC ;
- JSON des tâches/peers/results ;
- MCP resources/tools ;
- CLI exit codes/stdout/stderr ;
- fichiers d’état et recovery ;
- interfaces workload/plugin ;
- API BackEnd/FrontEnd.

### 9.2 Runtime natif

Aligner avec #247/#257 :

- crate contrats/canonicalisation ;
- crate identité/signatures ;
- crate stockage journal/CAS ;
- crate task book/anti-entropy ;
- crate transport/gossip/ICE ;
- crate admission locale/fairness ;
- API/CLI fin ;
- plugins C++ sans réseau ni clés privées.

### 9.3 Composition

Fusion doit fournir :

- manifest de composants ;
- allowlists d’artefacts ;
- SBOM et hashes ;
- matrice de compatibilité ;
- E2E sans VPS après bootstrap ;
- releases/rollback reproductibles.

## 10. Critères de fin de la sanitation

Le chantier est terminé lorsque :

- chaque fichier suivi a un cycle de vie et un owner ;
- aucune production ne démarre avec un secret de démonstration ;
- les checks requis sont inconditionnels ;
- les artefacts générés ne sont plus commités ;
- les images/bundles utilisent des allowlists ;
- les monolithes legacy ne sont plus des lieux d’ajout de fonctionnalités ;
- le task book fonctionne sans VPS ;
- BackEnd et FrontEnd possèdent des frontières typées ;
- le code archivé n’est plus présent sur `main` ;
- les issues ouvertes représentent du travail restant, pas des jalons déjà terminés.

## 11. Artefacts associés

- `AGENT_REMEDIATION_PLAN.md` : plan PR par PR pour un agent ;
- `ISSUE_TRIAGE.md` : décisions de backlog et dépendances ;
- `ISSUE_PLAN.json` : création/fermeture idempotente ;
- `generated-fast/` : inventaire exhaustif et exécution principale ;
- `generated/` : passe profonde et logs optionnels ;
- `generated-issues/` : preuve des créations/fermetures appliquées.
