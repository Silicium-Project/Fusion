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

## Suites qui lisent plusieurs dépôts privés

La CI native d'un composant ne compose que ce dépôt avec la politique Workbench.
Un test qui lit un autre composant privé ne doit donc pas être ajouté aux suites
déclarées dans `workspace.components.<id>.suites`. Déclarer une suite croisée
dans `tools/config/lanes.json`, lister chaque composant lu dans `sources`, et la
laisser hors des suites natives. `Integration` matérialise alors uniquement ces
sources épinglées, avec un jeton de lecture limité à ces dépôts.

Pour Network, `network-integration` couvre les tests locaux au dépôt ; les
assertions qui ont besoin du programme ou du SDK Solana sont isolées dans
`network-contract`, avec `sources: [network, solana]`. Le plan de composant
Network ne lance pas cette suite. Le plan privé Integration la lancera avec les
deux dépôts quand leurs pins intègreront les changements correspondants. Le
chemin attendu du SDK est `chain/sdk/src/index.ts`, selon la structure du dépôt
Solana ; ne pas réintroduire les anciens chemins du monorepo
`packages/solana-sdk`. La suite privée reste non qualifiée tant que les PR de
restauration des sources et de routage ne sont pas intégrées, puis que la
qualification complète ne passe pas depuis `Integration/main`. Les flags et le
quota doivent aussi être revérifiés avant ce run.

## Routage des suites publiques

Workbench sélectionne les suites publiques à partir des chemins réellement
modifiés. Une PR limitée à `docs/` lance la validation documentaire ; les
changements des workflows, outils partagés, contrats ou chemins inconnus
élargissent la matrice publique complète. Les fichiers propres à un composant
privé restent reportés vers Integration. `dev ci plan --scope public --base
origin/main --head HEAD --json` doit expliquer les chemins, les suites retenues
et les validations privées différées avant qu'un agent lance les contrôles.

La qualification native ne relance que les suites enregistrées pour le
composant concerné. Avant tout accès à sa source, le contrôle de budget exige
également un run Workbench réussi sur le SHA épinglé, avec `ci/required` et la
vérification de stockage tous deux terminés avec succès. Les suites publiques
ne sont donc pas reconstruites dans chaque dépôt privé ; Integration reste
responsable de la matrice complète avant livraison.

Le workflow réutilisable s'exécute dans le contexte d'Integration : son jeton
reste en lecture seule sur le dépôt appelant et ne gagne aucun droit sur
Workbench. Le reçu de métadonnées et sa signature détachée restent privés
pendant un jour. Le préflight `workflow_run` vérifie la signature et l'identité
du run avant de télécharger les binaires privés ; Workbench vérifie de nouveau
la signature avant d'accepter le reçu. Cette preuve ne publie ni ne déploie
encore de candidat. La signature Ed25519 est le mécanisme actuellement utilisé
pour le reçu privé ; elle n'ajoute pas de journal de transparence et fait de
l'accès en écriture à Integration sa frontière de confiance. Les attestations
natives GitHub sont disponibles pour les dépôts privés Enterprise
([documentation GitHub](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)), mais ne sont pas intégrées ni vérifiées par ce parcours. Une migration devra préserver les
contrôles de signature et être qualifiée séparément avant de retirer le reçu
Ed25519.

Le dépôt `Integration` exécute la qualification et appelle, dans le même run,
`private-integration-evidence.yml` via `workflow_call`. Le workflow réutilisable
conserve le contexte et le `GITHUB_TOKEN` du workflow appelant ; le jeton limité
à Integration, avec `Actions: read`, suffit pour vérifier le run et télécharger
ses artefacts. L'App `Silicium Integration Reader`, installée avec
`Actions: read` et `Metadata: read` sur `Integration`, n'est pas utilisée par
ce parcours. Ne pas créer une seconde App de lecture des preuves ni copier une
clé privée ou un Client ID d'App dans Workbench. Si l'architecture doit un jour
déplacer la collecte hors de ce run privé, documenter d'abord le besoin d'accès
inter-dépôts, le dépôt cible et les permissions minimales avant de créer une
App distincte.

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

L'inventaire public consulté le 27 octobre 2026 contient 47 releases et
218 assets ; l'API GitHub fournit un digest pour chacun, mais aucune release
n'a `manifest.json` ou `manifest.json.asc`. Les versions de plusieurs
releases de développement sont également dupliquées. Les digests GitHub ne
remplacent pas un manifeste signé qui lie les versions, les pins privés, le
canal et les assets. Le sélecteur de baseline refuse maintenant les versions
dupliquées, les tags inconnus et tout candidat dont la release la plus récente
du canal n'est pas signée, y compris les releases historiques aux anciens
formats de tags. `contracts/trust/release.gpg` est absent ; la livraison reste
bloquée jusqu'à la définition humaine d'une baseline et à la provision des
clés et de l'ancre approuvées. Aucune ancienne release n'est réécrite ou
déclarée signée rétroactivement.

## Activation après migration

Les workflows natifs utilisent `SILICIUM_COMPONENT_CI_ENABLED=1`. Integration
utilise `SILICIUM_INTEGRATION_ENABLED=1`. Les flags restent à zéro pendant la
préparation. Un composant n'active son flag qu'après la fusion de ses
nouveaux workflows ; les anciens workflows VPS sont retirés par les PR de
migration. Le blocage de quota du 26 octobre a été levé par l'essai Enterprise
(rapporté le 28 octobre, non revérifié). Un workflow suspendu ou ignoré ne
constitue jamais une qualification.

Dans le changement CI-01 en cours, `DesktopApp` sépare le flag de validation
`SILICIUM_COMPONENT_CI_ENABLED` du contrôle externe
`SILICIUM_MIRROR_ENABLED`, configuré à `0`. Activer les validations ne doit
jamais activer un push vers le dépôt Epitech. Le workflow du miroir ne reçoit
que `MIRROR_SSH_KEY`, sérialise les mises à jour et s'exécute sur un runner
GitHub borné dans le temps. Cette séparation ne sera effective qu'après la
fusion et la qualification des PR concernées.

Le changement proposé pour Network borne aussi sa concurrence : jusqu'à deux
jobs CodeQL et deux jobs Rust au premier stade, puis un job Solana et jusqu'à
trois tests parallèles. Le test Docker optionnel attend la fin des tests
principaux. Les jobs ont des limites de temps explicites ; ne pas augmenter
ces limites ou le parallélisme pour masquer une suite lente. Ce plafond n'est
pas actif sur `main` avant fusion et qualification.

Avant un lancement privé, exécuter le workflow CI de Workbench sur `main` et
attendre sa réussite. Integration vérifie automatiquement, avant de demander
le jeton Source Reader, que `main` porte encore le SHA retenu et que son unique
`ci/required` est terminé et réussi. Le contrôle public correspondant est
disponible localement avec `dev ci public-evidence --sha SHA --json` ; il ne
présente aucun jeton et bloque sur une preuve ancienne, absente ou incomplète.
Le job protégé `budget` observe tous les dépôts avec
l'App existante ; il vérifie une réserve de 392 Mio : 203 Mio d'archives de
livraison, 16 Mio pour le plan et les rapports privés, 1 Mio pour le reçu de
qualification, 64 Kio pour sa signature détachée, 1 Mio pour l'identité de candidat, jusqu'à 120 Mio pour
l'installateur Linux privé, 40 Mio pour l'installateur Windows privé, puis
jusqu'à 5 Mio pour le plan et les quatre rapports publics du run Workbench
lui-même. Cette réserve tient compte du fait que le contrôle de stockage
s'exécute avant les téléversements du run courant. Le contrôle applique un
plafond interne de 512 Mio quand l'API de l'organisation rapporte le plan
Enterprise et de 400 Mio dans les autres cas ; un plan absent ou inconnu retombe
sur le plafond plus bas. Si le jeton de l'App n'expose pas le plan (sortie
`plan_observed: null`), un humain peut déclarer le plafond dans la variable de
dépôt `SILICIUM_ORG_ARTIFACT_LIMIT_MIB` (entier de 400 à 512) ; toute autre
valeur est ignorée et un plan observé l'emporte toujours. Le plafond Enterprise reste volontairement petit au
regard des 50 Go de stockage Actions/Packages inclus sur ce plan
([quota](https://docs.github.com/en/billing/reference/product-usage-included)).
Il s'agit d'une garde de stockage, pas d'une limite de facturation. Les
workflows privés exigent que cette étape exacte ait réussi depuis moins de
quinze minutes et que son SHA corresponde
exactement au Workbench utilisé pour la qualification. Seul le push sur `main`
d'un dépôt composant accepte une preuve de moins de soixante minutes : la PR a
déjà passé le contrôle de quinze minutes avant la fusion, et un `main` rouge
pour une simple preuve périmée masque les vrais échecs. La fenêtre vient de
`SILICIUM_PROOF_MAX_AGE_MINUTES` (15 à 60, sinon 15) et ne s'applique qu'après
repin du composant sur un Workbench qui contient ce changement. Il s'agit d'une
observation bornée, pas d'un verrou global de stockage entre tous les dépôts.
Les campagnes complètes sont sérialisées, les rapports limités à 1 Mio et les
installateurs limités à 120/40 Mio expirent après un jour ; les caches privés
sont désactivés pendant la migration.

Cette preuve porte uniquement sur le stockage des artefacts. `private-budget.mjs`
ne lit pas le solde Actions inclus, ne calcule pas un montant facturable et ne
prouve pas qu'un plafond de dépenses bloque les dépassements. Le trial
Enterprise observé le 2026-10-28 ne donne pas accès à un budget avec arrêt à
0 $. Tant que cette limite existe, laisser les flags privés à zéro hors d'un
lancement manuel borné, vérifier le solde inclus juste avant le lancement et
comparer ce solde à tous les timeouts pondérés par type de runner. Le contrôle
Integration proposé dans la PR #4 demande un solde vérifié et bloque le run
avant tout jeton privé si la réserve calculée ne tient pas ; cette attestation
reste une vérification humaine et ne remplace pas un plafond GitHub.

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

Ne pas autoriser de dépenses Actions au-delà du quota inclus. Le trial
Enterprise donne jusqu'à 3 000 minutes standard hébergées
([conditions du trial](https://docs.github.com/en/enterprise-cloud%40latest/admin/overview/setting-up-a-trial-of-github-enterprise-cloud)) ;
ce quota doit être contrôlé séparément du stockage. Un plafond avec arrêt est
préférable lorsqu'il
est disponible. Si le plan ou le trial ne donne pas accès à ce contrôle, ne
prétendre pas que le compte est protégé contre les
dépassements : ne lancer que des workflows manuels dont la borne pondérée tient
dans le solde inclus, et laisser les flags à zéro en dehors de cette fenêtre.
L'épuisement du quota bloque la qualification. Ne pas utiliser de runner VPS,
copier des sources privées dans des workflows publics ou ouvrir un budget
facturable.

Pendant l'essai, fixer un seuil d'alerte humain sur le compteur de minutes et
sérialiser les campagnes complètes (Windows coûte plus cher que Linux). Ne
jamais lier d'abonnement Azure : cela met fin à l'essai et déclenche la
facturation. Avant l'échéance, une décision humaine choisit entre forfait payant
et retour à Free (2 000 minutes incluses, sans règles de branche privées ; à
confirmer auprès de GitHub). Le budget à zéro avec arrêt redevient alors la
règle.

## Synchronisation du Project 12 entre dépôts

La réconciliation publique `project-sync.yml` lit les PR explicitement liées de
Workbench, des cinq dépôts composants privés et d'Integration. Elle utilise
trois jetons d'installation éphémères séparés : le jeton Project existant pour
Workbench et `planning-private`, un jeton limité à Integration, puis un jeton
limité à BackEnd, FrontEnd, DesktopApp, Network et Solana. Les deux derniers
n'ont que `pull_requests: read` et `checks: read`. Le gate Workbench et celui
des composants sont `ci/required` ; celui d'Integration est
`integration/required`. Un jeton ou une réponse de dépôt manquante bloque la
réconciliation ; un gate absent, en attente, dupliqué ou produit par une autre
App laisse la PR en cours. Les données des PR privées ne sont jamais imprimées
dans les logs publics, qui ne contiennent que des totaux ; leurs références et
les blocages détaillés restent dans le Project 12 privé. La planification
existante toutes les quinze minutes détecte les PR privées, qui ne déclenchent
pas directement le workflow public. Le workflow ne clone ni n'exécute le code
des PR privées et ne reçoit aucun droit d'écriture sur ces dépôts ou sur le
Project depuis leurs jetons de preuve.

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

Au 28 octobre 2026, des rulesets actifs couvrent `main` dans Workbench,
Integration et les cinq dépôts composants. Integration exige
`integration/required` ; Workbench exige `ci/required`. Les rulesets composants
exigent une PR, la résolution des discussions et le check strict
`qualify / ci/required`, sans approbation imposée ni contournement. Ce nom suit
le [format GitHub des checks de workflows réutilisables](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/troubleshooting-rules#troubleshooting-required-status-checks)
(`job appelant / job réutilisable`) ; il faut encore prouver un succès sur le
SHA exact avant toute fusion. L'organisation est sur un essai Enterprise
temporaire ; revérifier les règles après son expiration et documenter tout changement de capacité. Les
membres autorisés à écrire restent une frontière de confiance ; maintenir des
accès limités et ne pas approuver de code extérieur pendant la stabilisation.

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
