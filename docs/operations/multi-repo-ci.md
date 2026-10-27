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
   run privé, le gate, le plan, les rapports, les cinq pins et les quatre
   sorties de compilation du SHA exact. Après succès, le job privé Integration
   signe les octets exacts du reçu avec Ed25519.
5. Conserver ces preuves privées. Les résultats publics de Workbench restent
   des preuves de ses seuls fichiers publics. Ne pas activer une publication
   à partir de ce seul gate.

Le workflow réutilisable s'exécute dans le contexte d'Integration : son jeton
reste en lecture seule sur le dépôt appelant et ne gagne aucun droit sur
Workbench. Le reçu de métadonnées et sa signature détachée restent privés
pendant un jour. Le préflight `workflow_run` vérifie la signature et l'identité
du run avant de télécharger les binaires privés ; Workbench vérifie de nouveau
la signature avant d'accepter le reçu. Cette preuve ne publie ni ne déploie
encore de candidat. La signature Ed25519 remplace l'attestation native
indisponible pour un dépôt privé sur GitHub Free ; elle n'ajoute pas de journal
de transparence et fait de l'accès en écriture à Integration sa frontière de
confiance.

La qualification native utilise un commit synthétique **local et temporaire**,
parent du SHA Workbench épinglé. Il permet de qualifier une nouvelle version du
composant sans modifier un checkout utilisateur. Les métadonnées enregistrent
les deux SHA originaux. Ce commit n'est ni une version intégrée ni un candidat
livrable ; il ne doit jamais être poussé.

## Autorisation des PR Workbench

Avant la qualification d'une PR interne, `tools/ci/authorize-internal-pull-request.mjs`
vérifie auprès de l'API GitHub que la tête appartient au même dépôt et que
l'auteur possède un droit `write`, `maintain` ou `admin`. Les lectures API
réessaient au maximum trois fois les erreurs réseau, timeouts et réponses HTTP
500/502/503/504, avec des pauses bornées de 250 ms puis 1 s. Les erreurs
d'autorisation 4xx échouent immédiatement. Le jeton `GITHUB_TOKEN` reste
éphémère et aucune réponse API ou valeur du jeton n'est journalisée.

Les actions GitHub sont épinglées par SHA immuable et alignées sur le registre
`tools/config/actions.json` : checkout v5, setup-node v6, upload-artifact v7,
download-artifact v8 et cache v6.1.0. `setup-node` désactive son cache implicite ;
seules les clés et frontières de confiance explicitement définies dans le
workflow contrôlent les caches.

## Audit public des règles du dépôt

`tools/config/workspace.json` fixe l'identité, la visibilité et la branche par
défaut attendues de Workbench ; `tools/config/repository-policy.json` décrit le
ruleset `Protect Main`. `dev ci policy --json` relit le dépôt et le ruleset via
l'API GitHub sans jeton ni secret, après avoir vérifié le registre local et les
pins. Le rapport contient le SHA de politique, l'heure locale de vérification,
les horodatages `Date` retournés par chaque réponse API, les écarts et les
limites de couverture. `contracts/ci/repository-policy-report-v1.schema.json`
fixe son format. Une réponse API refusée, limitée, invalide, sans horodatage ou
incomplète produit `blocked`, jamais un rapport propre.

La CI requise appelle ce contrôle lorsque le manifeste, son code, ses tests, le
lanceur ou le workflow CI changent ; les autres PR ne déclenchent pas cet appel
réseau. L'audit ne couvre que les métadonnées et règles visibles publiquement :
GitHub masque les acteurs de contournement et l'API de protection classique
exige une lecture administrative. Les dépôts privés, le Project et les
artefacts de release restent à vérifier par la réconciliation privée CI-09.

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
l'App existante ; il vérifie une réserve de 392 Mio : 203 Mio d'archives de
livraison, 16 Mio pour le plan et les rapports privés, 1 Mio pour le reçu de
qualification, 64 Kio pour sa signature détachée, 1 Mio pour l'identité de candidat, jusqu'à 120 Mio pour
l'installateur Linux privé, 40 Mio pour l'installateur Windows privé, puis
jusqu'à 5 Mio pour le plan et les quatre rapports publics du run Workbench
lui-même. L'enveloppe de signature consomme une partie de la marge de 6 Mio,
laissant environ 5,94 Mio. Cette réserve
tient compte du fait que le contrôle de stockage s'exécute avant les
téléversements du run courant. Les workflows privés exigent que cette étape
exacte ait réussi depuis moins de quinze minutes et que son SHA corresponde
exactement au Workbench utilisé pour la qualification. Il s'agit d'une
observation bornée, pas d'un verrou global de stockage entre tous les dépôts.
Les campagnes complètes sont sérialisées, les rapports limités à 1 Mio et les
installateurs limités à 120/40 Mio expirent après un jour ; les caches privés
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
