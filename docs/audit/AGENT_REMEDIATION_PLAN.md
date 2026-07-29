# Plan de remédiation exécutable par un agent

Ce document est l’ordre de travail obligatoire pour la refonte. Il ne remplace pas les issues : il indique comment les exécuter sans mélanger sanitation, migration d’architecture et nouvelles fonctionnalités.

## 1. Règles de fonctionnement de l’agent

1. Travailler sur une branche dédiée par dépôt et par issue.
2. Ne jamais modifier directement le VPS ou un checkout de production.
3. Ne jamais mettre à jour un gitlink Fusion avant fusion et validation du dépôt enfant.
4. Une PR = une intention principale.
5. Ne jamais mélanger formatage global et changement comportemental.
6. Conserver les anciens contrats jusqu’à l’existence de fixtures de compatibilité.
7. Ne pas ajouter de fonctionnalité au monolithe Python si elle appartient à Network#247/#257.
8. Ne pas appeler un composant réseau `scheduler` s’il assigne autoritairement des tâches. Le seul scheduling accepté est la politique locale d’admission/concurrence.
9. Ne pas archiver sur la base du nom d’un dossier.
10. Toute suppression exige : recherche de références, build/package scan, tests, owner et rollback.
11. Fournir dans chaque PR : problème, invariant, diff de comportement, tests, impact de compatibilité, rollback.
12. Arrêter une PR si son changement dépasse la frontière prévue ; ouvrir/séparer le travail au lieu d’élargir silencieusement.

## 2. Préambule obligatoire avant chaque PR

```bash
# Depuis Fusion
git status --short
git submodule status --recursive

# Dans le dépôt concerné
git status --short
git rev-parse HEAD
git grep -n "<symbole ou chemin modifié>"
```

Lire avant toute modification :

- `docs/audit/REPOSITORY_REFACTOR_REPORT.md` ;
- `docs/audit/generated-fast/inventory-summary.md` lorsqu’il existe ;
- `docs/audit/generated-fast/execution-summary.md` ;
- les logs correspondant au dépôt ;
- l’issue propriétaire et ses dépendances.

## 3. Gates transversaux

### Gate A — preuve de baseline

La PR ne commence pas si la composition exacte n’est pas enregistrée ou si les tests de référence ne sont pas exécutables.

### Gate B — contrat

Tout changement de format JSON/protobuf/CLI/fichier/HTTP/MCP doit :

- versionner le schéma ;
- fournir fixture avant/après ;
- indiquer compatibilité ascendante/descendante ;
- tester old reader/new writer et new reader/old writer lorsque requis.

### Gate C — production

Tout changement de déploiement doit valider :

- `docker compose config --quiet` ;
- image/bundle minimal ;
- absence de secrets dans le diff et les logs ;
- healthchecks ;
- rollback documenté.

### Gate D — suppression

Avant suppression :

```bash
git grep -n "<chemin|nom|entrypoint>" -- .
# Inspecter également workflows, Dockerfiles, scripts, package manifests et docs opérables.
```

Exécuter le packaging réel, pas seulement les tests unitaires.

## 4. Ordre de PR recommandé

## PR 01 — Baseline et manifeste de composants

**Dépôt :** Fusion  
**Issue :** `[Epic] Sanitize repositories and declare production/legacy lifecycle`

### Travail

- ajouter `docs/components.yaml` ou `components.json` ;
- déclarer chaque composant : repo, chemins, owner, statut, entrypoint, artefact, tests, déploiement ;
- ajouter les SHA de composition ;
- référencer les contrats externes ;
- ajouter une validation CI du schéma.

### Statuts autorisés

- `production` ;
- `supported-dev` ;
- `experimental` ;
- `legacy-supported` ;
- `archive-candidate` ;
- `generated` ;
- `documentation`.

### Interdictions

- aucune suppression ;
- aucun renommage massif ;
- aucun changement de runtime.

### Validation

```bash
python tools/validate-components.py docs/components.yaml
git submodule status --recursive
```

### Done

- tous les entrypoints de Compose et du desktop sont déclarés ;
- aucun artefact de production n’a de dépendance non déclarée ;
- le fichier est owner-reviewed.

## PR 02 — P0 configuration et secrets

**Dépôt :** Fusion, puis BackEnd si nécessaire  
**Issue :** `[Security] Remove demo credentials and hard-coded production endpoints`

### Travail

- remplacer les fallbacks de secrets par des variables obligatoires ;
- externaliser IP/domaines/ports ;
- ajouter `SILICIUM_ENV=development|production` ;
- ajouter une validation de config commune ;
- refuser wildcard CORS avec credentials en production ;
- pinner les images mutables, notamment `alpine:latest` ;
- documenter la rotation.

### Test négatif requis

```bash
set +e
docker compose -f deploy/compose/docker-compose.yml config
# La configuration production sans secrets doit échouer.
```

### Test positif requis

Utiliser uniquement des secrets éphémères d’audit, jamais une valeur réelle.

### Done

- grep de `demo-mesh`, `change-me`, IP du VPS et wildcard CORS vide dans les chemins production ;
- production refuse de démarrer sans secret ;
- local reste simple via exemples explicites.

## PR 03 — Quality gates inconditionnels

**Dépôt principal :** Network  
**Issue :** `[CI] Make quality gates unconditional and add formatter/linter ratchets`

### Travail initial

- retirer l’opt-in `SILICIUM_ENABLE_HOSTED_CI` pour les checks host-independent ;
- créer `.editorconfig` et `.gitattributes` cohérents ;
- ajouter une baseline de dette générée ;
- bloquer toute nouvelle violation sur fichiers modifiés.

### Outils

- Python : Ruff format/lint, Pyright ;
- Go : gofmt, go vet, staticcheck/golangci-lint ;
- Vue/TS : ESLint, Prettier, vue-tsc/tsc ;
- Rust : cargo fmt, clippy, test ;
- C/C++ : clang-format, clang-tidy ciblé ;
- Shell : ShellCheck, shfmt ;
- PowerShell : PSScriptAnalyzer ;
- Actions/YAML : actionlint, yamllint.

### Stratégie

1. rapport non bloquant ;
2. blocage sur lignes modifiées ;
3. correction composant par composant ;
4. suppression de la baseline lorsque vide.

### Done

- aucune variable cachée ne désactive les checks requis ;
- une PR ne peut pas augmenter la dette ;
- les différences Windows/Linux sont explicites.

## PR 04 — Retirer les artefacts générés de Git

**Dépôt :** Network  
**Issue :** `[Repository hygiene] Remove generated artifacts and archive verified legacy components`

### Travail

- supprimer le job `commit-coverage` ;
- conserver upload artifact et Pages ;
- retirer HTML/JSON/SVG générés de `main` ;
- ajouter les ignores appropriés ;
- corriger les liens README vers Pages/artifacts ;
- corriger les chaînes mojibake pertinentes.

### Interdiction

Ne pas supprimer simultanément du code source historique.

### Done

- une exécution coverage ne crée aucun diff Git ;
- Pages/artifacts restent accessibles ;
- le README est UTF-8 valide.

## PR 05 — Manifests minimaux de production

**Dépôt :** Fusion  
**Issue :** `[Build] Package only the declared production runtime`

### Travail

- créer une allowlist serveur ;
- créer une allowlist desktop Windows/Linux ;
- remplacer `COPY Network/` par des copies/build stages explicites ;
- ne plus copier tout `tools/`/`workloads/` sans manifeste ;
- produire `artifact-manifest.json` et SBOM ;
- vérifier les hashes et versions ;
- ajouter une denylist de garde : tests, coverage, caches, viewer, docs, clés, `.git`.

### Validation

```bash
docker compose -f deploy/compose/docker-compose.yml build \
  backend frontend dashboard orchestrator experiment-api

# Puis smoke test depuis les artefacts réduits.
```

### Done

- aucun fichier inattendu dans les images/installers ;
- smoke tests verts ;
- diff de taille et contenu publié dans la PR.

## PR 06 — Fixtures de compatibilité avant migration native

**Dépôt :** Network  
**Issue :** `[Refactor] Freeze compatibility contracts and characterization tests before native migration`

### Corpus minimal

- task/request envelope ;
- task statuses et terminal policy ;
- signatures Ed25519 ;
- task control cancel/expire ;
- claims et leases ;
- P2P references et content hashes ;
- peer snapshot et route table ;
- compute receipt ;
- MCP resources/tools ;
- protobuf RPC ;
- CLI exit/output ;
- restart/recovery.

### Travail

- créer `contracts/` et `tests/fixtures/contracts/` ;
- documenter source de vérité et version ;
- générer golden hashes ;
- ajouter tests Python/Rust/C++ croisés ;
- couvrir les erreurs et non seulement les happy paths.

### Done

- une implémentation native peut être comparée à Python sans réseau réel ;
- chaque rupture de contrat échoue en CI ;
- known bugs explicitement enregistrés, pas sanctifiés silencieusement.

## PR 07 — Task book natif et état dérivé

**Dépôt :** Network  
**Issues :** #257, #248, puis #250/#251

### Ordre interne

1. schéma d’événements canonique ;
2. hash/signature/chaîne par auteur ;
3. stockage durable ;
4. merge par union vérifiée ;
5. vue dérivée déterministe ;
6. heads/ranges anti-entropy ;
7. adapter Python en dual-write ;
8. test sans VPS.

### Invariants

- pas de leader obligatoire ;
- pas d’assignation par serveur ;
- chaque worker accepte localement ;
- pas de dépendance à l’horloge pour résoudre le livre ;
- payloads dans CAS, pas dans le journal ;
- reprise locale complète.

### Done

Tous les acceptance tests de #257 passent, notamment émission/exécution avec les endpoints VPS arrêtés.

## PR 08 — Transport et API natifs

**Dépôt :** Network  
**Issues :** #249, #250, #252, #216–#220

### Travail

- migrer gossip/identity/routing ;
- migrer ICE/TURN/relay derrière traits ;
- API/CLI versionnée ;
- conserver adaptateurs HTTP/MCP le temps de la compatibilité ;
- rate limits, timeouts, backpressure et diagnostics ;
- tests de perte/réordre/duplication/partition.

### Done

- preuve directe/relay/legacy dans les événements ;
- protocoles fuzzés ;
- rollouts mixtes testés ;
- aucune clé privée exposée au plugin workload.

## PR 09 — Refactor BackEnd typé

**Dépôt :** BackEnd  
**Issue :** `[Refactor] Extract typed network registry service and harden HTTP lifecycle`

### Structure cible

```text
internal/networkregistry/
  config.go
  models.go
  filesystem_repository.go
  service.go
  semver.go
```

### Travail

- structurer `NetworkTask`, `NetworkWorkload`, `NetworkPeer`, responses ;
- déplacer accès disque et paths ;
- injecter config ;
- handlers minces ;
- tests table-driven ;
- `http.Server` avec read/write/idle/header timeouts ;
- signaux et graceful shutdown ;
- contexte annulé pour le reconciler.

### Validation

```bash
gofmt -w <fichiers modifiés>
go vet ./...
go test ./...
go build -o /tmp/silicium-backend ./cmd/main.go
```

### Done

- aucun `map[string]any` à la frontière publique ;
- aucun path production dans le handler ;
- arrêt propre vérifié par test.

## PR 10 — Refactor FrontEnd typé

**Dépôt :** FrontEnd  
**Issue :** `[Refactor] Split dashboard into typed components and composables`

### Structure cible

```text
components/dashboard/
  DashboardSidebar.vue
  JobStats.vue
  JobsTable.vue
  NetworkTasksTable.vue
  SubmitJobModal.vue
  DeviceTypesChart.vue
composables/
  useJobs.ts
  useNetworkTasks.ts
  useCurrentUser.ts
  useSolanaBalance.ts
types/
  jobs.ts
  network.ts
  user.ts
```

### Travail

- client API authentifié central ;
- types de réponses ;
- erreurs UI observables ;
- supprimer `any`, placeholders et métriques fabriquées ;
- conserver le rendu avant redesign ;
- tests composants/composables ;
- Playwright desktop/mobile.

### Validation

```bash
npm ci
npm test
npm run build
npm run test:functional
```

### Done

- `pages/dashboard.vue` devient une page d’assemblage ;
- aucune donnée de démonstration présentée comme réelle ;
- contrat `workloads` testé.

## PR 11 — Inventaire et suppression des références legacy

**Dépôt :** Network

### Travail

Pour chaque candidat :

- produire une fiche : chemin, dernier usage, références, owner, remplacement ;
- supprimer d’abord les références/fallbacks ;
- faire passer le packaging et les tests ;
- marquer une release de dépréciation si externe ;
- seulement ensuite retirer le code.

### Candidats

- anciens splitter/executor historiques ;
- viewer si décision produit de retrait ;
- demos non utilisées ;
- `experimental/worker` après retrait du default ;
- Dockerfiles/scripts obsolètes.

### Non-candidats par défaut

- `worker/` ;
- `executor/` ;
- raytracer natif ;
- contrats/proto ;
- dashboard déployé ;
- fixtures nécessaires à la compatibilité.

### Done

- historique récupérable hors `main` ;
- aucun test/build/package ne référence les chemins retirés ;
- baisse mesurée de taille et de contexte.

## PR 12 — Retrait final Python et compatibilité

**Dépôts :** Network puis Fusion  
**Issues :** #253/#254

### Conditions d’entrée

- task book natif opérationnel ;
- API/transport natifs ;
- dual-write comparé ;
- artefacts natifs Windows/Linux ;
- rollback et mixed-version testés ;
- aucune fonctionnalité production exclusive au chemin Python.

### Travail

- retirer Python des images/bundles ;
- retirer wrappers legacy ;
- supprimer aioice/cryptography/OpenSSL uniquement s’ils ne sont plus requis par un autre composant ;
- mettre à jour SBOM, manifests, docs et updater ;
- release majeure ou politique explicite.

### Done

La définition de terminé de Network#247 est intégralement satisfaite.

## 5. Matrice de commandes finale

### Fusion

```bash
git submodule status --recursive
docker compose -f deploy/compose/docker-compose.yml config --quiet
npm --prefix apps/silicium-node ci
npm --prefix apps/silicium-node test
npm --prefix apps/silicium-node run build
cargo test --manifest-path apps/silicium-node/src-tauri/Cargo.toml
```

### Network

```bash
python -m compileall -q silicium tools networked workloads
python tools/check_utf8.py
python tools/check_i18n_locales.py --strict
python tools/style_check.py --rules cpp.interface_contract_naming
./silicium workload lint
./silicium workload golden --strict
./silicium test
cargo test --manifest-path workloads/raytracer/native/Cargo.toml
make -C executor
make -C worker test
npm --prefix silicium-layer-dashboard ci
npm --prefix silicium-layer-dashboard run build
```

### BackEnd

```bash
gofmt -l $(find . -name '*.go' -type f)
go vet ./...
go test ./...
go build -o /tmp/silicium-backend ./cmd/main.go
```

### FrontEnd

```bash
npm ci
npm test
npm run build
npm run test:functional
```

## 6. Format obligatoire du compte-rendu de l’agent

```markdown
## Invariant traité

## Fichiers modifiés

## Comportement avant/après

## Contrats affectés

## Preuves et commandes

## Résultats

## Risques résiduels

## Rollback

## Issue suivante débloquée
```

L’agent ne doit jamais conclure « tests passent » sans fournir la commande et le résultat observable.
