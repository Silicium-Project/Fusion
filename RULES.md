# RULES.md — règles de maintenance du projet Silicium

Chaque règle est vérifiable. La colonne « Contrôle » dit comment elle est (ou sera) appliquée automatiquement.
Une règle sans contrôle automatique est vérifiée en revue de PR. Exceptions : listées et datées dans
`.rules-exceptions` (à vider, jamais à allonger).

## 1. Dépôt et git
| # | Règle | Contrôle |
|---|---|---|
| G1 | Aucun fichier suivi > 1 Mo ; aucune extension `zip, exe, dll, msi, onnx, safetensors, gguf, ppm, pfx` ; aucune image > 300 Ko dans `public/` | job `repo-hygiene` + hook pre-commit |
| G2 | Aucun artefact généré suivi (`dist/`, `target/`, `node_modules/`, `.output/`, `.silicium/`) | `repo-hygiene` (`git ls-files` contre motifs) |
| G3 | Le `.gitignore` de Fusion ne contient aucune ligne `Network/`, `BackEnd/`, `FrontEnd/` | `repo-hygiene` |
| G4 | Même `.gitattributes` et `.editorconfig` dans les 4 dépôts ; pas de CRLF hors `*.ps1`/`*.cmd` | `git ls-files --eol` en CI |
| G5 | Fichiers de code/doc < 400 lignes (hors lockfiles, fixtures, locales, `tests.rs`) ; fonctions < 80 lignes | job `max-lines` (+ ESLint `max-lines`, golangci `funlen`) |
| G6 | Aucun doublon de fichier (hash) hors copies déclarées et contrôlées | `repo-hygiene` |
| G7 | Pas de rapport, journal ou archive dans le dépôt (`Rapport-*`, `docs/archive` nouveaux) | revue |
| G8 | Branches : `main`, `dev`, et branches de travail `<type>/<sujet>` supprimées après merge ; toute branche sans commit depuis 30 jours est archivée en tag `archive/<nom>` puis supprimée | réglage GitHub « delete head branches » + revue mensuelle |

## 2. Commits, versions, composition
| # | Règle | Contrôle |
|---|---|---|
| C1 | Conventional Commits `type(scope): description` en anglais | commitlint (hook `commit-msg` + job PR) |
| C2 | Auteur ∈ {Thom, Luis, bot de release} ; jamais `Claude`, `Codex`, `noreply@anthropic.com`, `unknown` | commitlint + `.mailmap` |
| C3 | `[skip ci]` interdit sur `feat`, `fix`, `ci` et sur tout commit qui touche `.github/`, `deploy/`, `*.ps1` ou un gitlink | job `ci-fast` (`git diff --name-only`) |
| C4 | Un gitlink de Fusion pointe sur un commit contenu dans la branche du canal du sous-module (`dev` / `main`) | `submodule-ci-gate` (`merge-base --is-ancestor`) |
| C5 | Montée de sous-module = commit seul `chore(submodule): bump <Repo> a..b`, via PR | revue |
| C6 | Chaque PR référence une issue rattachée à un jalon (`Closes #N`), sauf label `chore-no-issue` | action de vérification de PR |
| C7 | Une version produit unique (Fusion) : `vX.Y.Z` (prod), `vX.Y.Z-dev.N` (dev), toujours croissantes ; release immuable (échec si le tag existe) ; tag créé sur le commit construit (`target_commitish`) | test du workflow de release |
| C8 | Promotion `dev`→`main` par PR à chaque jalon, puis back-merge immédiat ; aucun commit direct sur `main` | protection de branche |

## 3. CI/CD et serveur
| # | Règle | Contrôle |
|---|---|---|
| D1 | Aucun job self-hosted dans un workflow déclenché par `pull_request` ou par un push hors `main`/`dev`/tags | `deploy/ci/check-workflows` en CI |
| D2 | Tout job self-hosted ou de déploiement déclare un `environment:` protégé (approbation de Thom pour `production`) | `check-workflows` |
| D3 | `permissions: {}` au niveau du workflow, `timeout-minutes` sur chaque job, jamais `secrets: inherit` | `zizmor` / `check-workflows` |
| D4 | Toute action externe épinglée par SHA ; Dependabot actif (actions, cargo, npm, gomod) | `zizmor` + Dependabot |
| D5 | `actionlint` et `shellcheck -S warning` verts ; `run:` ≤ 15 lignes (sinon script versionné et testé) ; workflow < 250 lignes | job `lint-ci` |
| D6 | Le VPS ne compile rien : il déploie des images GHCR taguées par SHA et des binaires construits en CI (`grep "build:" deploy/compose/*.yml` vide) | `lint-ci` |
| D7 | Clé de signature des mises à jour jamais sur une machine qui exécute du code CI | revue + doc d'exploitation |
| D8 | Sauvegarde PostgreSQL quotidienne hors VPS, réussie depuis < 26 h ; restauration testée à chaque jalon | `post-deploy-check.sh` |
| D9 | Chaque service Compose a image épinglée, healthcheck, limite mémoire et rotation des logs | `lint-ci` (script sur le YAML) |

## 4. Sécurité
| # | Règle | Contrôle |
|---|---|---|
| S1 | Aucun secret versionné, même « de démo » ; compose utilise `${VAR:?required}` | gitleaks (pre-commit + CI, scan complet hebdomadaire) |
| S2 | Audits de dépendances bloquants (haute non justifiée = échec) : `govulncheck`, `cargo audit`/`cargo deny`, `npm audit --omit=dev --audit-level=high`, `pip-audit` | jobs CI par composant |
| S3 | Toute route `/…/{id}` a un test « autre utilisateur → 404 » ; toute route admin vérifie un rôle | test qui parcourt la table des routes |
| S4 | L'API de contrôle du nœud n'est jamais publiée hors loopback/réseau Docker ; aucun chemin absolu accepté | test d'intégration + `post-deploy-check` |
| S5 | Toute donnée P2P entrante : taille max, quota par pair, autorisation avant de servir | tests du nœud |
| S6 | En-têtes prod : HSTS, CSP, `X-Content-Type-Options`, pas de version serveur ; refresh token en cookie `HttpOnly` | `post-deploy-check.sh` |
| S7 | Tauri : `csp` non nulle + `capabilities/*.json` | check `jq` en CI |

## 5. Code
| # | Règle | Contrôle |
|---|---|---|
| K1 | Rust : `fmt --check`, `clippy --workspace --all-targets --all-features -D warnings`, `unwrap_used` interdit hors tests, `cargo machete` | CI Network / app |
| K2 | Rust : aucune E/S ni `.await` long dans la boucle `select!` du nœud ; canaux bornés ; collections purgées | revue + bench `perf-smoke` |
| K3 | Go : `gofmt`, `go vet`, `staticcheck`, `go test -race`, `go mod tidy -diff`, golangci-lint (`errcheck`, `funlen`, `forbidigo` sur `os.Getenv` hors config) | CI BackEnd |
| K4 | Go : migrations SQL versionnées pour tout changement de modèle ; transitions de statut des jobs conditionnelles et centralisées | test de schéma + grep CI |
| K5 | TS/Vue : `nuxi typecheck`, ESLint + Prettier, pas de `fetch(` hors `services/api.ts`, pas de texte visible en dur | CI FrontEnd |
| K6 | i18n : parité fr/en/de et aucune clé inutilisée | tests vitest |
| K7 | Solana : une seule source pour program ID, mint et barème ; décodage par IDL ; `anchor test` + clippy en CI | job `solana-consistency` |
| K8 | Couverture minimale : 70 % sur auth, paiements (`chainproof`), appairage, annulation ; 70 % `utils/` FrontEnd | seuils de couverture |

## 6. Performances et exploitation
| # | Règle | Contrôle |
|---|---|---|
| P1 | Balayage périodique du nœud < 50 ms à 5 000 tâches (release) | job `perf-smoke` (`sweep_bench`) |
| P2 | Pas de polling < 2 s sans backoff ni test de visibilité ; préférer SSE | grep CI (`setInterval` via composable commun) |
| P3 | Endpoints de liste paginés et filtrés côté serveur | revue |
| P4 | Nœud et BackEnd exposent `/metrics` (Prometheus) ; toute PR qui touche taskbook/gossip/polling joint le bench avant/après | revue |
| P5 | Budget bundle FrontEnd : entrée ≤ 120 Ko gzip | `size-limit` en CI |
| P6 | Chez le volontaire : priorité basse, budget CPU, pause sur batterie/activité utilisateur | test de `spawn_worker()` |

## 7. Documentation et architecture
| # | Règle | Contrôle |
|---|---|---|
| A1 | Doc = code : un changement de port, variable, route, workload, crate ou workflow met à jour la doc dans le même commit | tests « OpenAPI couvre les routes », « env documentées », liens morts |
| A2 | Toute exception aux règles de langage ou d'architecture passe par un ADR (`docs/architecture/adr/`) | revue |
| A3 | Docs en français avec accents ; code et commits en anglais | `check_utf8.py` |
| A4 | Pas de nouvelle crate, service ou module `pub` sans consommateur réel ; code mort supprimé, pas contourné | `cargo machete`, `deadcode`, `staticcheck U1000` |
