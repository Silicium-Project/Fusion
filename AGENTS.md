# Silicium — instructions communes aux contributeurs et agents

Lire [la carte et les procédures IA](docs/ai/README.md) avant une modification.
Les instructions d'un sous-dossier précisent ses invariants ; les commandes
communes ci-dessous restent la référence locale et GitHub.

## Carte

- `apps/web` : Nuxt/Vue/TypeScript ; `apps/api` : comptes et accès au réseau, Go.
- `apps/node` : application Tauri/Vue et supervision locale, Rust/TypeScript.
- `network` : workspace Rust du réseau P2P et des workloads.
- `chain/solana` : programme Anchor, toolchain isolée et tests localnet.
- `packages/solana-sdk` : SDK TypeScript.
- `contracts` : contrats partagés ; `infra` : exploitation et livraison.
- `tools` : commandes communes ; `docs` : procédures normatives et archives.

## Commencer une tâche

1. `./dev doctor --profile <composant>` (`.\dev.ps1` sous Windows).
2. Consulter le Project 12 ; respecter dépendances, préparation et WIP.
3. Utiliser une branche courte `<type>/<issue>-<objet>` et une PR brouillon.
4. Lire l'`AGENTS.md` du composant ; préserver tout changement local existant.
5. `./dev ci plan --base origin/main --head HEAD --json` décrit les validations.
6. Exécuter les suites applicables avec `./dev test --suite <id>` ; la CI
   utilise exactement les mêmes commandes. Un prérequis absent reste bloquant.
7. Documenter contrats, exemples, erreurs et preuves dans la même PR.

`./dev capabilities --json` est l'inventaire des commandes implémentées.
Les commandes GitHub modificatrices demandent `--apply`. Préparer leur résultat
vérifiable avant application. Une acceptation de tâche et une promotion en
production restent des décisions humaines explicites.

## Invariants

- Sécurité, coût puis vitesse : aucune validation obligatoire ne disparaît pour
  accélérer la CI. Un test absent, ignoré ou annulé n'est pas une réussite.
- Le site est une porte d'accès ; les évolutions ne doivent pas rendre le P2P
  dépendant du fonctionnement du site ou de l'automatisation GitHub.
- Aucun build ni campagne de tests sur le VPS applicatif. Les livraisons passent
  par GitHub ; le VPS vérifie et applique des artefacts immuables.
- Runtime réseau Rust, API Go, interfaces/SDK TypeScript ; Python pour l'outillage.
  L'ancien runtime Python, ses CLI/MCP, la chaîne C++ et Qt ne doivent pas revenir.
- Les instructions anciennes de `docs/archive` décrivent un historique. Elles
  ne doivent pas servir de procédure actuelle ni de preuve de disponibilité.
- Ne pas créer ou changer un programme Solana, son ID ou ses autorités dans une
  tâche de CI/infrastructure. Les clés de wallets restent hors de la CI générale.
- Garder stables les identifiants d'application et les chemins des données
  installées. Le dossier embarqué `Network/` reste compatible avec les clients.
- Ne jamais commiter secrets, configurations réelles, wallets, ledgers, caches,
  données utilisateur ou journaux sensibles. Ne pas les inclure dans un rapport.

## Qualité et fin de tâche

Privilégier des modules courts, des responsabilités explicites et les contrats
aux points d'extension réels. Ne pas introduire d'abstraction sans besoin concret.
Rapporter SHA, commandes, codes de sortie, tests réellement exécutés, artefacts
et limites observées. La réussite d'un contrôle statique ne démontre pas un
parcours installé ni un déploiement. Une fusion de PR ne vaut pas acceptation.
