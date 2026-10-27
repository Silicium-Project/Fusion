# Qualification des dépôts séparés

Lire [la décision](../architecture/multi-repo.md) et les
[commandes communes](../development/commands.md).

## Parcours normal

1. Modifier un composant dans sa branche native et ouvrir une PR avec
   `Refs: https://github.com/Silicium-Project/Workbench/issues/NUMERO`.
2. Sa CI privée appelle `component-ci.yml` de Workbench par SHA complet et
   crée une composition locale avec ce même SHA de politique. Les suites et
   rapports utilisent `dev`, comme sur le poste du contributeur.
3. Faire intégrer la PR native par un mainteneur humain. Préparer une PR
   Workbench modifiant gitlink et `components.lock.json` ensemble.
4. Après sa fusion humaine, déclencher `qualification.yml` dans Integration,
   sur `main`, avec le SHA complet de Workbench. Le workflow vérifie que le
   commit appartient à `main`, récupère exactement les cinq pins, puis exécute
   toutes les suites du registre. `integration/required` exige chaque rapport.
   Après le gate, Integration appelle par SHA complet le workflow public
   `private-integration-evidence.yml`. Celui-ci revérifie via l'API GitHub le
   run privé, le gate, le plan, les rapports et les cinq pins du SHA exact.
5. Conserver ces preuves privées. Les résultats publics de Workbench restent
   des preuves de ses seuls fichiers publics. Ne pas activer une publication
   à partir de ce seul gate.

Le workflow réutilisable s'exécute dans le contexte d'Integration : son jeton
reste en lecture seule sur le dépôt appelant et ne gagne aucun droit sur
Workbench. Il conserve un reçu de métadonnées privé pendant un jour. Ce reçu
n'est ni une signature, ni une publication, ni une preuve permanente de
livraison ; aucun workflow ne construit ou ne déploie encore depuis lui.

La qualification native utilise un commit synthétique **local et temporaire**,
parent du SHA Workbench épinglé. Il permet de qualifier une nouvelle version du
composant sans modifier un checkout utilisateur. Les métadonnées enregistrent
les deux SHA originaux. Ce commit n'est ni une version intégrée ni un candidat
livrable ; il ne doit jamais être poussé.

## Publication séparée

L'App `Silicium Source Reader` reste strictement en lecture seule. Ne pas ajouter
de droits d'écriture à cette App pour publier une livraison. Le manifeste
`tools/config/delivery-publisher-app-manifest.json` décrit une App séparée,
sans webhook et installée uniquement sur `Workbench` :

- `contents: write` pour publier les seuls assets explicitement publics dans
  une release Workbench ;
- aucun droit sur les sources privées, issues, projets, checks, déploiements,
  membres ou secrets.

Ce fichier prépare la configuration ; l'App n'est pas créée ni installée. Le
déploiement protégé s'appuiera sur l'événement de publication d'une release,
sans donner à l'App le droit `Actions: write`. Les images GHCR sont publiées par
le `GITHUB_TOKEN` à portée du dépôt Integration avec `packages: write`, après
configuration d'un accès de paquet compatible. Les GitHub Apps ne remplacent
pas le jeton de registre accepté par GitHub Packages. Les clés APT/RPM/release
et le trust anchor public manquent encore : ne pas activer le chemin ni
provisionner l'App de publication avant validation des scopes, secrets et
formats publics. Aucun secret de publication ne va sur le runner VPS ou dans
l'App Source Reader.

## Activation après migration

Les workflows natifs utilisent `SILICIUM_COMPONENT_CI_ENABLED=1`. Integration
utilise `SILICIUM_INTEGRATION_ENABLED=1`. Les flags restent à zéro pendant la
préparation ; les Actions des anciens composants restent suspendues jusqu'à
l'intégration de leurs nouveaux workflows et la disponibilité du quota privé.
Un workflow suspendu ou ignoré ne constitue jamais une qualification.

Avant un lancement privé, exécuter le workflow CI de Workbench sur `main` et
attendre sa réussite. Le job protégé `budget` observe tous les dépôts avec
l'App existante ; il vérifie une réserve de 232 Mio : 203 Mio d'archives de
livraison, 16 Mio pour le plan et les rapports privés, 1 Mio pour le reçu de
qualification, 1 Mio pour l'identité de candidat, puis jusqu'à 5 Mio pour le
plan et les quatre rapports publics du run Workbench lui-même. Les 6 Mio
restants couvrent les marges d'archivage. Cette réserve tient compte du fait
que le contrôle de stockage s'exécute avant les téléversements du run courant.
Les workflows privés exigent que cette étape exacte ait réussi depuis moins
de quinze minutes. Il s'agit d'une observation bornée, pas d'un verrou global
de stockage entre tous les dépôts. Les campagnes complètes sont sérialisées,
les rapports limités à 1 Mio et expirent après un jour ; les caches privés
sont désactivés pendant la migration.

Les suites `api`, `web`, `node-ui` et `network-integration` téléversent aussi
leurs sorties de compilation privées sous `delivery-<suite>-<run_attempt>`.
Le vérificateur de Workbench exige les quatre noms exacts, enregistre leurs
identifiants GitHub, digests SHA-256 et tailles dans le reçu privé ; le nom
du reçu inclut lui aussi le numéro de tentative. Il rejette
un artefact manquant, expiré, dupliqué ou hors budget. Le reçu ne contient pas
les binaires ; ceux-ci restent dans Integration une journée.

La tentative de réception dans Workbench a été supprimée : même un runner
temporaire public ne doit pas manipuler les sorties privées. Le workflow privé
Integration doit télécharger les artefacts de son propre run, revérifier le
reçu par la politique Workbench, puis les extraire et les assembler dans le
même dépôt privé. Le staging refuse les chemins inattendus, les liens
symboliques, les réécritures et les identités d'artefact incomplètes. La
construction du candidat et la signature/publication restent des étapes
distinctes et non activées.

Le budget Actions de l'organisation doit rester à zéro avec blocage du
dépassement. Les runners standards des dépôts privés consomment le quota
inclus ; le statut public de Workbench ne change pas cette règle. Son
épuisement bloque la qualification. Ne pas utiliser de runner VPS, copier des
sources privées dans des workflows publics ou ouvrir un budget facturable.

## Accès aux sources

L'organisation interdit la création de clés SSH de déploiement ; cette politique
reste conservée. L'App **Silicium Source Reader** existe et est installée
uniquement sur BackEnd, FrontEnd, DesktopApp, Network et Solana. Son unique droit
explicite est `contents: read` ; métadonnées en lecture implicites. Aucun droit
Project, Actions, secrets ou déploiement, aucune écriture de code. Ne pas la
recréer ni élargir ses droits.

Dans Integration, `SOURCE_APP_CLIENT_ID` et `SOURCE_APP_PRIVATE_KEY` sont des
secrets chiffrés déjà provisionnés. Vérifier leur présence par nom seulement ;
ne jamais lire, imprimer ou copier leur valeur. Ne pas réutiliser le jeton
personnel du propriétaire ni la clé de l'App du Project. Aucune clé de wallet,
de signature ou d'upgrade Solana n'est utilisée. Workbench et les CI natives
ne reçoivent pas cette clé. En cas de rotation, générer la clé dans les réglages
de l'App et remplacer directement le secret GitHub ; ne pas transmettre la clé
dans un chat, une issue, un commit ou un artefact.

Chaque suite privée crée un jeton d'installation de courte durée, limité aux
dépôts déclarés comme sources de cette suite ; le contrôle des contrats demande
les cinq dépôts. Le workflow vérifie que le SHA Workbench est sur `main`.
`materialize.mjs` n'accepte que Integration privé sur `main`, vérifie le manifeste,
le gitlink et le lock, puis utilise une récupération peu profonde à ce SHA.
L'authentification Git HTTPS est limitée aux
processus de récupération et n'est pas persistée dans Git. Le jeton n'est pas
placé dans l'environnement des commandes applicatives ni dans un artefact. L'action
révoque son jeton à la fin du job. Une absence d'App bloque la récupération ;
aucun accès du propriétaire n'est utilisé en secours. La création/installation
initiale de l'App exige une session propriétaire GitHub et reste une étape humaine.

GitHub Free ne fournit pas les mêmes protections sur les dépôts privés que sur
Workbench public. Les conventions PR/CODEOWNERS ne sont pas présentées comme
des protections serveur effectives. Les membres autorisés à écrire dans ces
dépôts constituent donc une frontière de confiance ; maintenir des accès
limités et ne pas y approuver de code extérieur pendant la stabilisation.

## Livraison et miroir Epitech

Le reçu privé vérifie les preuves mais ne transporte aucun artefact de livraison.
La reprise du transport des binaires vers la signature/publication reste
bloquée avant sa propre qualification. Les anciens workflows publics
`release`, `campaigns` et `mirror-epitech` ne peuvent plus construire ou publier
une composition incomplète. Les flags de livraison restent à zéro.

La qualification privée seule ne démontre pas les signatures, les installations
APT/DNF/Windows, un déploiement, un rollback ni une acceptation d'issue. La
production conserve ses approbations indépendantes et les services existants
ne sont pas modifiés par ce chantier.
