# AGENTS.md — consignes pour les agents IA (Claude, Codex, Copilot…) et les contributeurs

Lis ce fichier, puis `RULES.md`, puis le `AGENTS.md` du sous-module concerné, **avant toute modification**.

## Contexte
Silicium est un réseau de calcul distribué (projet EIP Epitech) : des PC de particuliers calculent
des sous-tâches, d'autres nœuds les vérifient, l'orchestrateur assemble le résultat ; Solana Devnet
trace jobs, réputation et récompenses (jeton de test SIL, sans valeur).
Équipe : Thom (lead), Luis. Canaux : `dev` (VPS privé via WireGuard) et `prod` (`main`).

**Priorité actuelle : stabilité, sécurité et démo fiable.** Aucune nouvelle fonctionnalité sans issue
rattachée à un jalon (M0 → M5). Périmètre de démo : raytracer, sha256, recherche dans des documents
(embedding), traitement IA (Ollama). Le catalogue Hugging Face est expérimental et désactivé par défaut.

## Carte du dépôt (Fusion = composition)
| Chemin | Type | Langage | Contenu |
|---|---|---|---|
| `Network/` | sous-module | Rust (+ Anchor, SDK TS) | nœud `p2p_node`, calcul, workloads, programme Solana |
| `BackEnd/` | sous-module | Go | API : comptes, jobs, catalogue, appareils, trace Solana |
| `FrontEnd/` | sous-module | Nuxt 3 / TS | site |
| `apps/silicium-node/` | dossier | Rust (Tauri) + Vue | app desktop qui installe et supervise le nœud |
| `apps/silicium-ai-runtime/` | dossier | Python (**exception**, ADR-0001) | moteur du catalogue IA expérimental |
| `deploy/` | dossier | shell, Compose, systemd | serveur, canaux, VPN |
| `.github/workflows/` | dossier | YAML | CI/CD |
| `docs/` | dossier | Markdown (FR) | doc transverse, ADR |

Chaque sous-module est un dépôt distinct avec sa branche `dev` et sa CI. Une modification d'un composant
se committe **dans le sous-module**, jamais dans Fusion.

## Langages
- Rust pour tout ce qui s'exécute chez l'utilisateur ou sur le serveur. Go pour le BackEnd.
  TypeScript pour le FrontEnd et le SDK Solana. Python uniquement pour l'outillage (`Network/tools/dev`, tests).
- N'ajoute aucun Python, Node.js ou autre interpréteur exécuté chez l'utilisateur ou en prod.
  Si une tâche IA manque, propose candle ou ort.
- Doc en français avec accents ; code, identifiants et messages de commit en anglais.

## Commandes
| Composant | Construire | Tester (obligatoire avant de proposer un commit) |
|---|---|---|
| Network | `cargo build --release --locked -p p2p_node` (dans `Network/`) | `cargo fmt --all --check` · `cargo clippy --workspace --all-targets -- -D warnings` · `cargo test --workspace --locked` |
| Solana | `anchor build` (dans `Network/solana-layer`) | `anchor test` |
| BackEnd | `go build ./cmd/...` | `gofmt -l .` (vide) · `go vet ./...` · `go test ./...` |
| FrontEnd | `npm ci && npm run build` | `npx nuxi typecheck` · `npx vitest run` |
| App desktop | `npm ci && npm run build` (dans `apps/silicium-node`) | `npm test` · `cargo test --manifest-path apps/silicium-node/src-tauri/Cargo.toml` |
| Fusion (deploy) | — | `python3 -m pytest -q deploy/tests` · `actionlint` · `shellcheck -S warning deploy/**/*.sh` |

Rapporte le résultat exact de chaque commande. Si une commande échoue faute de réseau ou d'outil,
dis-le : ne la déclare jamais réussie.

## Commits
- Conventional Commits : `type(scope): description` (anglais, impératif, ≤ 72 caractères).
  Types : feat, fix, refactor, perf, test, docs, ci, build, chore, revert.
- Auteur : l'utilisateur git configuré (Thom). Jamais d'auteur ou de trailer `Claude`, `Codex`, `Copilot`.
- Un sujet par commit. Une montée de sous-module est un commit à part :
  `chore(submodule): bump <Repo> <old7>..<new7>` avec la liste des commits en corps.
- Référence l'issue : `Refs #N` ou `Closes #N`.
- **Jamais `[skip ci]`.**

## Interdits absolus
- `git add .` / `git add -A` à la racine de Fusion : ajoute les fichiers un par un, par chemin.
- Pousser, fusionner, créer/supprimer une branche ou un tag, ouvrir une PR, réécrire l'historique
  (`rebase` de branche publiée, `push --force`, `filter-repo`) — sauf demande explicite.
- Pointer un gitlink de Fusion sur un commit absent de la branche du canal du sous-module
  (`dev` pour Fusion `dev`, `main` pour Fusion `main`). Fusionne d'abord la branche de travail.
- Committer un secret (`.env`, keypair Solana, clé, jeton, mot de passe, **même « de démo »**) ou un
  artefact (`target/`, `node_modules/`, `dist/`, `.silicium/`, `.output/`, binaire, modèle, ZIP,
  image > 200 Ko, `*.ppm`). Si un asset est nécessaire, demande où le publier.
- Créer un rapport, journal ou plan dans le dépôt sans demande (ils vont dans le projet Claude ou une issue).
- Réintroduire ce qui a été supprimé : runtime Python du nœud, CLI `silicium`, MCP, OpenSSL, TURN/`demo-mesh`,
  dashboard réseau, staking passif, marché SIL / prix fiat / swap, crédits pour l'IA.
- Modifier `deploy/release/channels.json`, les workflows de déploiement, la config VPN ou `.gitmodules`
  sans demande explicite.

## Sécurité
- CI : aucun job `runs-on: self-hosted` déclenché par `pull_request` ou par une branche quelconque ;
  jamais `secrets: inherit` ; `permissions` minimales et `timeout-minutes` sur chaque job ;
  chaque `uses:` épinglé par SHA complet (`# vX.Y.Z` en commentaire) ; pas d'expression
  `${{ github.event.* / inputs.* }}` dans `run:` (passe par `env:`) ; pas de `sudo` dans un workflow ;
  secrets dans `$RUNNER_TEMP` avec `trap` de suppression, jamais dans `$HOME`.
- BackEnd : toute route qui lit une ressource par ID filtre `user_id` en SQL et a un test « autre utilisateur → 404 ».
  Toute route d'administration vérifie un rôle admin.
- Réseau : tout chemin reçu d'une API ou du réseau est relatif et confiné ; toute donnée réseau a une taille
  maximale, un timeout, un quota par pair et un contrôle d'autorisation **avant** de servir des données.
- FrontEnd : pas de `v-html` ; jetons jamais dans `localStorage` ni dans un cookie non `HttpOnly`.
  Aucune transaction signée sans validation des programmes, du payeur et du cluster.
- Tauri : `csp` non nulle ; toute commande `invoke` déclarée dans une capability.

## Règles par composant
- **Nœud (Rust)** : aucune E/S disque, hachage de gros fichier ou `.await` long dans la boucle `select!` de
  `p2p-node/src/main.rs` (spawn + canal borné). Jamais `.send().await` vers un canal que la boucle courante est
  seule à vider. Aucun parcours de `book.events()` dans un code périodique. Toute collection qui grossit avec les
  tâches/pairs a une purge testée. Formats signés (`TaskEvent`, `signing_bytes`) : version incrémentée + test de
  compatibilité. `tracing` et `thiserror`, pas de `println!` ni d'erreurs en chaînes.
- **BackEnd (Go)** : pas d'`os.Getenv` hors de la config centrale (et documente la variable) ; aucune écriture du
  statut d'un job hors de la transition conditionnelle ; aucune écriture en base dans un GET ; aucune erreur GORM
  ignorée ; format d'erreur unique `{error, message}` i18n ; OpenAPI mise à jour dans le même commit ; pas de
  nouvelle lecture de fichiers internes du nœud (passe par `/v1`).
- **FrontEnd (Nuxt)** : tout appel API passe par `services/api.ts` / `authorizedFetch` ; aucun texte visible en dur
  (clés fr/en/de) ; aucune adresse Solana en dur (lire `utils/solanaConfig.ts`) ; décodage des comptes via l'IDL ;
  tokens de `assets/css/tokens.css` et composants `Ui*` ; direction visuelle `design/mockups/precision-v4-2026-10-20`.
- **Solana** : ne change jamais un program ID, un mint ou un barème dans un seul dépôt ; toute instruction a une
  contrainte sur chaque signataire, un test d'appelant tiers, un test de valeurs extrêmes et un chemin de fermeture
  des comptes ; aucune valeur de test (TTL, cooldown, stake 0) en constante de production. Toute incitation modifiée
  s'accompagne d'un paragraphe « que fait un acteur rationnel malhonnête ? ».
- **App desktop** : commandes Tauri `async` ; chemins de données via un seul module ; tout processus de calcul passe
  par la fonction commune (priorité basse, `env_clear()`, limites) ; jamais de kill par sous-chaîne de ligne de
  commande ; aucun hôte/IP/peer id en dur (variables de build issues de `channels.json`).
- **CI/déploiement** : pas plus de 15 lignes de logique dans un `run:` (script versionné dans `deploy/ci/` ou action
  composite, avec test) ; reproduire un échec avec le script avant de corriger le YAML ; ne pousser vers `main`/`dev`
  depuis un workflow que par PR.

## Qualité
- Fichiers < 400 lignes ; fonctions courtes à rôle unique ; en-tête de module ; doc des éléments publics ;
  README par dossier ou crate. Si tu dépasses, découpe dans le même commit.
- Chaque changement de comportement a un test. Chaque changement de port, variable d'env, route, workload ou
  workflow met à jour la doc dans le même commit.
- Pas de nouvelle dépendance sans justification dans le message de commit.

## Avant de rendre la main
Résume : fichiers modifiés, commandes lancées et leur résultat exact, docs mises à jour, ce qui reste à faire.
