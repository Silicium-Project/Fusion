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
5. Conserver ces preuves privées. Les résultats publics de Workbench restent
   des preuves de ses seuls fichiers publics. Ne pas activer une publication
   à partir de ce seul gate.

La qualification native utilise un commit synthétique **local et temporaire**,
parent du SHA Workbench épinglé. Il permet de qualifier une nouvelle version du
composant sans modifier un checkout utilisateur. Les métadonnées enregistrent
les deux SHA originaux. Ce commit n'est ni une version intégrée ni un candidat
livrable ; il ne doit jamais être poussé.

## Activation après migration

Les workflows natifs utilisent `SILICIUM_COMPONENT_CI_ENABLED=1`. Integration
utilise `SILICIUM_INTEGRATION_ENABLED=1`. Les flags restent à zéro pendant la
préparation ; les Actions des anciens composants restent suspendues jusqu'à
l'intégration de leurs nouveaux workflows et la disponibilité du quota privé.
Un workflow suspendu ou ignoré ne constitue jamais une qualification.

Avant un lancement privé, exécuter le workflow CI de Workbench sur `main` et
attendre sa réussite. Le job protégé `budget` observe tous les dépôts avec
l'App existante ; il vérifie la marge de stockage avec une réserve de 210 Mio.
Les workflows privés exigent que cette étape exacte ait réussi depuis moins
de quinze minutes. Il s'agit d'une observation bornée, pas d'un verrou global
de stockage entre tous les dépôts. Les campagnes complètes sont sérialisées,
les rapports limités à 1 Mio et expirent après un jour ; les caches privés
sont désactivés pendant la migration.

Le budget Actions de l'organisation doit rester à zéro avec blocage du
dépassement. Les runners standards des dépôts privés consomment le quota
inclus ; le statut public de Workbench ne change pas cette règle. Son
épuisement bloque la qualification. Ne pas utiliser de runner VPS, copier des
sources privées dans des workflows publics ou ouvrir un budget facturable.

## Accès aux sources

L'organisation interdit la création de clés SSH de déploiement ; cette politique
reste conservée. L'App **Silicium Source Reader** est créée et installée
uniquement sur BackEnd, FrontEnd, DesktopApp, Network et Solana, conformément au
[manifeste minimal](../../tools/config/source-app-manifest.json). Son unique droit
explicite est `contents: read` ; métadonnées en lecture implicites. Aucun droit
Project, Actions, secrets ou déploiement, aucune écriture de code. Ne pas recréer
l'App ni élargir son périmètre.

Les secrets chiffrés `SOURCE_APP_CLIENT_ID` et `SOURCE_APP_PRIVATE_KEY` sont
présents dans Integration. Vérifier seulement leur présence par nom ; ne jamais
lire, afficher ou copier leurs valeurs. Ne pas réutiliser le jeton personnel du
propriétaire ni la clé de l'App du Project. Aucune clé de wallet, de signature ou
d'upgrade Solana n'est utilisée. Workbench et les CI natives ne reçoivent pas
cette clé.

Au 26 octobre 2026, le workflow manuel est sur Integration/main, mais
`SILICIUM_INTEGRATION_ENABLED` n'est pas configuré et aucun run n'a été lancé.
Le quota inclus d'Actions privées est épuisé alors que le dépassement reste
bloqué à zéro. Vérifier à nouveau le quota avant le premier run ; ne pas
activer de dépassement ni utiliser le VPS comme runner. Le détail à jour est
conservé dans le [README privé d'Integration](https://github.com/Silicium-Project/Integration#current-status).

Pour éliminer les chemins CI vers les runners VPS, Backend CI, Frontend CI,
Network CI et Create GitHub Release (qui ciblent les runners `self-hosted`) ont
été désactivés dans GitHub le 26 octobre 2026. Solana SBF build, exécuté sur un
runner GitHub mais redondant avec la qualification privée, ainsi que l'ancien
miroir Epitech lié au dépôt DesktopApp ont aussi été suspendus. Aucun run
n'était en attente ou actif lors de ces suspensions. Les PR
de restauration des cinq composants contiennent les nouveaux wrappers vers
`component-ci.yml`, épinglés à un SHA Workbench public et protégés par
`SILICIUM_COMPONENT_CI_ENABLED`. Ils restent en brouillon ; tant qu'ils ne sont
pas intégrés et que le quota n'est pas disponible, aucune qualification privée
ne doit démarrer. La variable `SILICIUM_COMPONENT_CI_ENABLED` vaut explicitement
`0` dans chacun des cinq dépôts. Après intégration et vérification du quota, ne
réactiver que ces nouveaux wrappers.

La création, l'installation ou la rotation de l'App exigent une décision et une
session du propriétaire GitHub. Si elles deviennent nécessaires, reprendre le
nom et l'URL du manifeste, désactiver webhooks et abonnements d'événements,
garder `Contents: Read-only` et « Only select repositories », puis vérifier la
présence des secrets par leur nom. Transférer toute nouvelle clé directement
depuis GitHub vers les secrets Integration ; ne jamais la coller dans un chat,
une issue, un commit ou un artefact.

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

La reprise du transport des artefacts privés vers la signature/publication
reste bloquée avant sa propre qualification. Les anciens workflows publics
`release`, `campaigns` et `mirror-epitech` ne peuvent plus construire ou publier
une composition incomplète. Les flags de livraison restent à zéro.

La qualification privée seule ne démontre pas les signatures, les installations
APT/DNF/Windows, un déploiement, un rollback ni une acceptation d'issue. La
production conserve ses approbations indépendantes et les services existants
ne sont pas modifiés par ce chantier.
