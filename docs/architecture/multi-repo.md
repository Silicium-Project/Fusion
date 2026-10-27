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

`tools/config/workspace.json` déclare les responsabilités et suites.
`components.lock.json` fixe un SHA complet par composant ; `.gitmodules` fixe
les URL et les gitlinks Git portent exactement ces SHA.

- `dev workspace status` vérifie cette cohérence sans accès réseau.
- `dev workspace init --component ID --apply` récupère le pin déclaré avec les
  droits Git de l'utilisateur ; aucun checkout existant divergent n'est écrasé.
- `dev workspace verify --materialized` exige cinq checkouts propres aux pins.
- `dev workspace pin --component ID --revision SHA --apply` récupère ce commit,
  détache le checkout et prépare le gitlink et le lock pour une PR d'intégration.
- Les développements du composant se font dans sa branche native ; ne pas
  commiter ses sources directement dans Workbench.

## Sources propres à DesktopApp

Le runtime d'inférence local utilisé par l'application de bureau est versionné
dans le dépôt privé `DesktopApp/silicium-ai-runtime`. Ses ressources Python,
manifestes et verrous de dépendances font partie de ce composant et sont
embarqués par DesktopApp au moment de la compilation. Workbench ne conserve
aucune copie active de ces sources : seul le gitlink `apps/node` identifie la
révision qui les contient.

Une modification du runtime suit donc le même flux que le reste de DesktopApp :
PR native, qualification disponible, mise à jour du gitlink et de
`components.lock.json` dans une PR Workbench. La révision de migration actuelle
`6a233f1c421358143238c25562c45ad607b85721` est encore la tête de la PR native
DesktopApp #1 ; elle n'est pas intégrée à `main` et les Actions privées sont
désactivées par le budget. Ce pin de travail ne constitue ni une qualification
privée ni une livraison. L'ancien chemin public reste visible dans l'historique
de Workbench, qui n'a pas été réécrit.

## Qualification et coût

Le registre commun conserve les suites applicatives. Les scopes sont :

| Scope | Preuve fournie |
| --- | --- |
| `public` | Documentation, outillage, sécurité et PowerShell de Workbench |
| `component:ID` | Politique commune et suites du composant ; consommateurs différés |
| `integration` | Toutes les suites PR et vérification des sources des cinq composants |
| `local` | Routage conservateur des fichiers touchés et des consommateurs |

Les suites différées sont explicites dans le plan. Elles ne sont pas considérées
comme réussies. Les rapports portent le SHA Workbench, la politique, le scope et
les cinq pins ; un rapport ancien ou d'un autre scope échoue au gate.
Les tests de contrat nécessitant des sources privées sont conservés dans les
suites privées `workspace-sources` et `solana`.

Les workflows publics ne récupèrent aucun composant et n'ont pas de clé de
lecture des sources privées. Les workflows natifs utilisent une version précise
de la politique publique. La qualification complète s'exécute dans Integration.
Les GitHub runners privés consomment le quota de l'organisation. Son budget
Actions reste à zéro avec arrêt des dépassements ; quota épuisé = blocage, sans
repli VPS ni exécution de nouvelles sources privées dans des logs publics.

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
