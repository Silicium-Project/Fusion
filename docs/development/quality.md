# Normes et validations du dépôt

Les imports Git et déplacements sont antérieurs aux commits de normalisation.
Le runtime reste en Rust, l'API en Go et les interfaces en TypeScript/Vue.
Anchor garde sa toolchain isolée. Aucun C/C++ maintenu par Silicium n'entre
dans le périmètre actuel ; Clang reste un prérequis de compilation de dépendances.

## Commandes communes

```sh
npm ci --prefix tools/quality --ignore-scripts --no-audit --no-fund
./dev format
./dev format --write
./dev test --suite tooling
./dev test --suite powershell
```

`format` vérifie Prettier et les règles de correction ESLint ; `--write`
applique uniquement le formatage. Le paquet `tools/quality` a son propre
lockfile et des versions exactes. Il ne remplace pas les gestionnaires des
applications. Le formatage initial est isolé des imports dans l'historique.

La suite tooling valide le registre, les contrats, les scénarios du plan CI,
les sources TypeScript/Vue/modules et les scripts Bash. Le compilateur de
chaque application reste l'oracle des types ; Nuxt exécute explicitement
`nuxi typecheck`. Les sorties compilées du SDK sont générées et ignorées par
Git ; `npm run build` les prépare avant utilisation ou publication.

ShellCheck 0.11.0 est verrouillé par les empreintes de l'archive et du binaire.
Un cache corrompu bloque ; seule sa copie dans `.artifacts/tools` peut être
retirée. Les fichiers d'environnement réels ne sont pas suivis par ShellCheck :
les exceptions locales `source=/dev/null` l'indiquent explicitement.

La suite PowerShell utilise le parseur et PSScriptAnalyzer 1.25.0, téléchargé
dans un répertoire jetable après vérification SHA-256. Elle tourne sur Windows
2022 ; une exécution portable Linux peut compléter ces résultats mais ne
qualifie ni l'installateur Windows ni les comportements propres à Windows.

Rustfmt/Clippy et Gofmt/Vet sont définis dans les suites runtime/API. Actionlint
et les scans d'historique restent dans security. La documentation normative
est reliée depuis `docs/README.md` et `docs/ai/README.md`. Les archives gardent
leurs anciens chemins comme trace historique et ne décrivent pas les commandes
actuelles.

Les suites natives desktop qualifient les unités Rust avec `TAURI_CONFIG`
fixant `bundle.resources=[]`. Elles n'embarquent pas un faux runtime et ne
recompilent pas le réseau pour tester le superviseur. Le packaging garde sa
configuration normale et doit fournir les vrais binaires réseau ; les tests
d'installation contrôlent leur présence. Une réussite des unités ne qualifie
donc pas l'installateur.

La suite infrastructure rend les deux canaux Compose avec des fichiers
temporaires, des digests factices et des valeurs de test. Les variables
obligatoires de production restent obligatoires. Aucun conteneur n'est démarré
par ce contrôle. Un Compose autonome vérifié peut être indiqué localement avec
`SILICIUM_COMPOSE_BINARY=/chemin/docker-compose` lorsque le plugin manque.

## Python de CI

La version est épinglée à 3.11.17 ; `network/requirements-dev.txt` verrouille
Pytest et ses dépendances Linux avec leurs empreintes de wheels. Le bootstrap
installe avec `--require-hashes`. Une modification nécessite un téléchargement
depuis PyPI, la revue des métadonnées et hashes, et les suites Python réseau et
infrastructure. Ne pas remplacer ce lock par `pytest>=...` dans le pipeline.

## Outils Solana

`chain/solana/Cargo.lock` est versionné et généré avec Rust 1.89.0. Les racines
Anchor sont fixées à 0.32.1 ; les commandes de validation gardent `--locked`.
Le CLI Anchor est le binaire de la release upstream, vérifié par SHA-256 et
associé au commit du tag dans `anchor-tools.json` et `upstreams.json`. Son cache
est revérifié avant exécution. Il n'est plus recompilé à chaque bootstrap.
La construction du programme SBF et tous les tests localnet restent exécutés.

Le validateur 2.3.0 n'accepte pas `--rpc-bind-address` et ses services RPC/faucet
écoutent largement malgré `--bind-address`. La qualification le lance donc
dans des namespaces réseau/PID jetables, avec uniquement le loopback. Les
tests n'ont aucune sortie Devnet. `unshare`, `ip` et les namespaces utilisateur
doivent être disponibles localement. Sur les runners GitHub éphémères qui les
restreignent, seul le bootstrap du namespace utilise `sudo -n`, puis `setpriv`
retire les groupes/privilèges avant les tests. Aucun repli sur le réseau hôte
n'est prévu. La sortie du namespace détruit son arbre de processus.

Le comportement du validateur est vérifié dans
[la source Agave épinglée](https://github.com/anza-xyz/agave/blob/v2.3.0/test-validator/src/lib.rs#L977).

## Preuves et limites

L'outillage JavaScript contrôle aussi les identifiants non déclarés avec
ESLint. Un test exécute réellement `dev test --suite docs` dans un sous-processus
et vérifie son rapport complet ; les seuls tests de fonctions internes ne
suffisent pas à qualifier le lanceur commun.

La suite API réutilise son binaire déjà construit pour démarrer un serveur
loopback avec SQLite jetable, clé JWT aléatoire et paiements désactivés. Elle
vérifie santé, identité, contrat OpenAPI effectivement servi et refus d'accès
aux appareils sans session. Elle ne lance aucun runtime P2P et ne touche aucune
base utilisateur. La réussite ne qualifie donc pas PostgreSQL ni le réseau.

Un test obligatoire absent, ignoré ou nul échoue. Le contrôle final compare
SHA, politique et rapports ; les releases embarquent leurs entrées dans
`qualification.json`. Toujours indiquer les commandes et plateformes réellement
exécutées : un lint réussi ne prouve pas une installation ou un déploiement.

Le plan enregistre aussi chaque commande, répertoire, type de contrôle et
variable déclarée. Un rapport amputé d'un test ou qui le rebaptise en simple
contrôle échoue. Les suites non applicables portent leur justification.
Supprimer ou changer une obligation existante dans une PR exige une revue
indépendante, puis l'autorisation administrateur `SILICIUM_POLICY_MIGRATION_SHA`
égale au SHA de cette PR. Un agent ne doit pas se donner cette autorisation.
Les ajouts de contrôles et la conservation des obligations de l'ancienne
politique restent automatiques ; la CI utilise la variable administrateur.
