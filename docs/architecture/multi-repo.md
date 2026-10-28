# ADR — Workbench et composants indépendants

Décision du propriétaire, 25 octobre 2026 : revenir à des dépôts indépendants,
renommer Fusion en **Workbench** et conserver son historique public. Cette
décision remplace l'organisation monorepo ; elle ne change ni le protocole P2P,
ni les identités installées, ni les autorités Solana.

## Visibilité et provenance

Workbench reste public. Network, BackEnd, FrontEnd, DesktopApp et Solana restent
privés. Integration conserve les sources et journaux de qualification croisée
privés. Les anciens commits publics, issues, discussions et releases de Fusion
restent publics, conformément au choix explicite du propriétaire. Aucun filtre
d'historique, force-push ou dépôt de remplacement n'est utilisé.

L'identifiant GitHub de Workbench reste `1304063299`. Ne pas recréer un dépôt
`Fusion` : cela casserait les redirections. Les appels `uses:` de workflows et
les URL canoniques sont actualisés explicitement. Les identifiants produit,
chemins de stockage, clés, programmes blockchain et services existants restent
indépendants du nom du dépôt.

## Import précédent et réexport

L'import précédent est conservé dans [import-map.json](import-map.json).
Le rattachement des historiques de #317 a été restauré par #319, fusionnée par
commit de merge. Le retour aux dépôts natifs est préparé depuis
`ff14db3c666eb9f355f59bfa908a48f0e7a44e6c`, puis le déplacement mécanique du SDK
dans `chain/sdk`. Le programme et le SDK restent dans le même dépôt Solana,
avec leurs workspaces Rust/Anchor et TypeScript distincts.

Chaque export contient `.silicium-provenance.json` : commit et arbre source,
chemin d'origine, parents natifs préservés et ancien `main`. Les commits
applicatifs sont rattachés aux historiques natifs sans squash. Les anciens
travaux et PR restent disponibles ; aucune PR active n'est fermée implicitement.
Les modifications locales antérieures sont conservées dans leur checkout.

## Une composition reproductible

`tools/config/workspace.json` est le registre versionné des dépôts, propriétaires,
visibilité, branches par défaut, chemins et suites ; son contrat strict est
`contracts/workspace/registry-v1.schema.json`. `components.lock.json` porte son
propre contrat `contracts/workspace/pins-v1.schema.json`. `tools/config/lanes.json`
définit les dépendances de validation ; `contracts/catalog.json` définit les
propriétaires de contrats, consommateurs, versions et suites de compatibilité.
`components.lock.json` fixe un SHA complet par composant ; `.gitmodules` fixe
les URL et les gitlinks Git portent exactement ces SHA. Les versions et règles
de distribution sont dans `tools/config/delivery.json` et les schémas de
`contracts/ci/`.

Modifier un dépôt, une branche, un chemin ou une visibilité dans une PR
Workbench, avec les tests de schéma et la revue des composants affectés. Le
changement doit mettre à jour les exemples, consommateurs et instructions IA
qui dépendent du champ. Tout ajout, retrait ou changement de type d'un champ
exige une nouvelle version du schéma, l'actualisation du document `$id` et la
migration des consommateurs dans la même séquence de PR. Une période de
transition peut accepter deux versions, mais chaque consommateur doit déclarer
explicitement celle qu'il lit ; aucun schéma ne devine ou convertit un champ.
Un changement de pin modifie ensemble le gitlink et `components.lock.json`. Les
dépendances et consommateurs sont modifiés dans leur registre propriétaire,
pas recopiés dans un second fichier. Integration consomme ces sources depuis
un SHA Workbench exact et en conserve le digest dans le rapport de
réconciliation.

Les identifiants `owner` et `co_owners` du catalogue des contrats désignent les
responsables du contenu. Les schémas, le registre, les pins et leurs tests sont
maintenus avec Workbench ; `.github/CODEOWNERS` doit diriger les changements de
`contracts/` et `tools/config/` vers les responsables du dépôt. Aucun bot ne
réécrit les pins ni ne modifie automatiquement une visibilité ou une identité.

- `dev workspace status` vérifie cette cohérence sans accès réseau.
- `dev workspace init --component ID --apply` récupère le pin déclaré avec les
  droits Git de l'utilisateur ; aucun checkout existant divergent n'est écrasé.
- `dev workspace verify --materialized` exige cinq checkouts propres aux pins.
- `dev workspace pin --component ID --revision SHA --apply` récupère ce commit,
  détache le checkout et prépare le gitlink et le lock pour une PR d'intégration.
- Les développements du composant se font dans sa branche native ; ne pas
  commiter ses sources directement dans Workbench.

## Qualification et coût

Le registre commun conserve les suites applicatives. Les scopes sont :

| Scope          | Preuve fournie                                                       |
| -------------- | -------------------------------------------------------------------- |
| `public`       | Documentation, outillage, sécurité et PowerShell de Workbench        |
| `component:ID` | Politique commune et suites du composant ; consommateurs différés    |
| `integration`  | Toutes les suites PR et vérification des sources des cinq composants |
| `local`        | Routage conservateur des fichiers touchés et des consommateurs       |

Les suites différées sont explicites dans le plan. Elles ne sont pas considérées
comme réussies. Les rapports portent le SHA Workbench, la politique, le scope et
les cinq pins ; un rapport ancien ou d'un autre scope échoue au gate.
Les tests de contrat nécessitant des sources privées sont conservés dans les
suites privées `workspace-sources` et `solana`.

Les workflows publics ne récupèrent aucun composant et n'ont pas de clé de
lecture des sources privées. Les workflows natifs utilisent une version précise
de la politique publique. La qualification complète s'exécute dans Integration.
Les GitHub runners privés consomment le quota inclus de l'organisation. Le
trial Enterprise observé le 28 octobre 2026 inclut des minutes Actions, mais
exclut les budgets avec limite d'usage : il n'existe donc pas de coupe-circuit
GitHub à 0 $ pendant cet essai. L'objectif reste zéro dépassement payé. Avant
chaque exécution privée, vérifier le solde inclus et le pire cas pondéré du
plan, ne lancer qu'un run manuel borné et refermer son flag après l'exécution.
Une attestation de quota n'est pas un plafond de facturation. Si la réserve ne
peut pas être confirmée, bloquer le run ; aucun repli VPS ni transfert de code
privé vers les workflows publics n'est autorisé.

## Activation et limites

Les exports et le changement de structure sont proposés en PR. Les pins peuvent
viser leurs branches de migration avant fusion ; une publication exige ensuite
leur intégration humaine et une qualification privée complète. Aucun pin de
branche de travail ne constitue une release acceptée.

Le changement de périmètre public nécessite l'autorisation administrative du
SHA précis via `SILICIUM_POLICY_MIGRATION_SHA`. Les agents ne se donnent pas cette
autorisation. Le gate ne transforme pas l'ancienne qualification monorepo en
preuve des futurs composants privés.

Les anciens workflows publics de construction et campagnes applicatives restent
inactifs. L'ancien `release.yml` Workbench, qui mélangeait la réception
d'artefacts privés et le contexte public, a été retiré. Une prévalidation
Integration liée à la qualification privée est proposée, mais les builds,
signatures, contrôles d'installation et rollbacks restent à qualifier. Les
verrous de livraison restent fermés ; la production conserve ses approbations
humaines. Les services déjà installés ne sont pas redémarrés par cette migration.
