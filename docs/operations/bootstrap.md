# État et activation contrôlée des workflows

## État actuel

Workbench (anciennement Fusion) est public. Sa CI qualifie le périmètre public
et `ci/required` rend obligatoires les suites prévues par le plan ; les suites
applicatives privées restent exclues de ce résultat. Les workflows privés
distincts des dépôts composants et d'Integration n'obtiennent aucune preuve
quand ils sont ignorés ou désactivés. Aucun runner CI n'est hébergé sur le VPS.

La qualification complète des composants est isolée dans le dépôt privé
[Integration](https://github.com/Silicium-Project/Integration), via son workflow
manuel **Full private integration**. Elle exige un commit Workbench intégré à
`main`, les sources privées à leurs SHA exacts, un flag d'activation et un
budget Actions disponible avec plafond de dépense à zéro. Au dernier contrôle
du dépôt Integration, aucune variable d'activation n'était définie. La dernière
capture de facturation fournie montrait 2 000 minutes privées utilisées sur
2 000 incluses ; cette capture n'est pas une mesure actuelle du quota. Vérifier
le compte et le plafond avant tout lancement. Ne pas contourner un refus, payer
un dépassement ni utiliser un runner VPS.

La commande `dev ci authorize-private` a été supprimée : elle contrôlait une
fenêtre dans Workbench et ne pouvait pas autoriser le workflow privé distinct
d'Integration.

La synchronisation du Project est active (`SILICIUM_PROJECT_AUTOMATION_ENABLED=1`).
Le premier apply GitHub du 27 octobre a réussi sur 139 issues Workbench et
modifié 9 statuts et 139 champs « Blocage » ; les 32 éléments de `planning-private`
restent exclus. Le dry-run qui a suivi n'a annoncé qu'une transition et un
blocage supplémentaires après la qualification de la PR #325. Les champs
« Blocage » saisis manuellement sont préservés. Publication et déploiement
restent désactivés (`SILICIUM_DELIVERY_ENABLED=0`), tout comme les diagnostics
distants (`SILICIUM_DIAGNOSTICS_ENABLED=0`).

Le protocole de drainage des workers reste à qualifier ; le programme
d'application bloque un changement d'image réseau plutôt que d'interrompre une
tâche active.

## Qualification privée

Lancer **Full private integration** uniquement depuis Integration, après avoir
vérifié le quota et les flags. La procédure et les conditions d'acceptation
font autorité dans le [README Integration](https://github.com/Silicium-Project/Integration/blob/main/README.md).
Le résultat doit identifier le SHA Workbench, les cinq pins privés, toutes les
suites requises et leurs rapports. Un run public Workbench ou un job ignoré ne
remplace pas cette qualification et n'autorise ni publication ni déploiement.

## Protections GitHub observées

Le rapport d'exposition a été validé et Workbench est public. La protection
effective de `main` exige une PR, le contrôle `ci/required` strict et la
résolution des discussions. Elle s'applique aux administrateurs et interdit le
force-push et la suppression. Le mode mainteneur unique conserve zéro revue
requise. Les anciens runners CI VPS sont retirés ; aucun build, test ou
packaging ne revient sur le VPS.

Les environnements de production et de signature restent limités à `main` et
exigent une validation humaine indépendante. Les workflows de contributeurs
externes ne sont pas approuvés pendant la stabilisation. L'audit des membres et
des droits hérités de l'organisation reste nécessaire avant toute modification
du rôle d'écriture par défaut.

### Mode mainteneur unique

Ce mode remplace l'exigence initiale de revue indépendante, avec l'accord
explicite du propriétaire le 25 octobre 2026. `main` conserve une protection
de PR avec zéro approbation exigée ; ne pas supprimer cette protection entière.
Les options imposant une revue CODEOWNERS ou une approbation du dernier push
sont désactivées. Les conversations, la CI stricte liée à l'App GitHub Actions,
l'application aux administrateurs et l'interdiction des pushes forcés et des
suppressions restent actives. Aucun nouveau droit de contournement n'est créé.

Vérifier aussi `repos/Silicium-Project/Workbench/rules/branches/main` : les règles
s'ajoutent à la protection classique. L'ancienne règle `Protect Main` exigeait
elle aussi une approbation et celle du dernier push ; seule cette exigence est
adaptée, avec les éventuels approbateurs spécifiques et l'approbation des
changements non attribués. Les autres règles, conditions et acteurs sont conservés.

`node tools/admin/protect-public.mjs` prépare cette configuration ; `--apply`
l'applique après autorisation. Il refuse de modifier une règle héritée ou
partagée avec d'autres branches et vérifie les obligations effectives. Ses
environnements de production conservent les approbateurs et l'interdiction
d'auto-approbation : ce changement concerne l'intégration dans `main`.
Une fusion et une acceptation d'issue restent des décisions humaines distinctes.

## Signatures et registre

- `signing-development` / `signing-production` : secrets `APT_SIGNING_KEY`,
  `RPM_SIGNING_KEY`, `RELEASE_SIGNING_KEY`, `UPDATE_SIGNING_KEY` ; variables correspondantes
  `*_FINGERPRINT` et `DOWNLOAD_BASE_URL`.
- Exporter les clés existantes par un canal sécurisé. Les scripts refusent une
  empreinte différente et ne génèrent jamais de nouvelle autorité de confiance.
- Installer la clé publique de livraison dans `contracts/trust/release.gpg` et
  `/etc/silicium[-dev]/release-trust.gpg` après revue de son empreinte.
- Vérifier que les paquets GHCR `api`, `web`, `network` sont publics avant
  l'activation. Leur publication utilise les digests OCI, avec provenance.
- Aucun wallet utilisateur, clé worker ou autorité d'upgrade Solana ne doit
  être exporté vers ces environnements.

Le bootstrap des clés et la signature Windows doivent être qualifiés avant une
diffusion aux utilisateurs. Une clé privée ne doit jamais être placée dans une
issue, une sortie de commande ou un commentaire de PR.

Les clés publiques APT/RPM et leurs empreintes sont conservées dans
`contracts/trust/packages.json`. L'auto-update conserve la clé publique du
client dans `contracts/trust/update.json` ; la clé actuellement utilisée par
le serveur diffère et ne doit pas la remplacer sans migration de confiance.
La clé de signature Windows est limitée aux environnements
`windows-signing-development` / `windows-signing-production`, avec une empreinte
de certificat `WINDOWS_SIGNING_THUMBPRINT` vérifiée avant et après signature.

## VPS

Préserver les ports, volumes et racines définis dans `infra/release/channels.json`.
Le PostgreSQL déployé reste en version majeure 16. Le fichier Compose local de
l'API garde sa version majeure 18 et son volume distinct.

L'adoption initiale doit être exécutée via un workflow GitHub protégé, après
inventaire des services réellement en place :

1. Sauvegarder le rendu Compose et les digests actuels dans un répertoire privé.
2. Créer un compte `silicium-deploy`, un répertoire d'arrivée séparé et une clé
   SSH dédiée. Limiter sudo à l'entrée d'application root, sans shell arbitraire.
3. Installer `infra/delivery/apply.py` comme fichier root non modifiable par ce
   compte, `/usr/local/sbin/silicium-apply`.
4. Préparer une référence de retour arrière dans `delivery/current.json`, avec
   un répertoire complet `infra/compose`, `candidate.env`, `downloads`,
   `release_id`, `manifest_digest` et `network_image`. Vérifier cette référence.
5. Transformer le répertoire downloads en pointeur atomique après sa copie
   vérifiée. Ne jamais supprimer son contenu existant.
6. Qualifier le drainage, le canari et le retour arrière du runtime P2P avant
   d'autoriser le premier changement de son image. L'ancien runtime systemd
   ne doit pas être désactivé sur la seule base d'un healthcheck.

`development` / `production` contiennent `DEPLOY_SSH_KEY`, et les variables
`DEPLOY_SSH_HOST`, `DEPLOY_SSH_KNOWN_HOSTS`. L'empreinte SSH est épinglée ; aucun
`ssh-keyscan` non vérifié n'entre dans le workflow.

## GitHub App du Project

Le manifeste est `tools/config/project-app-manifest.json`. L'App doit avoir
uniquement les permissions de lecture nécessaires aux preuves, la gestion des
issues et des Projects. Aucun secret de livraison et aucun droit d'écriture du
code ne lui sont attribués. Pour mesurer le budget global, l'installation doit
viser **tous les dépôts** de l'organisation. Le jeton `Project sync` est ensuite
limité à `Workbench` et `planning-private`, avec `checks: read`, `issues: read`,
`pull_requests: read` et `organization_projects: write`. Le jeton budget demande
seulement `actions: read` ; un JWT de courte durée vérifie que l'installation
couvre bien toute l'organisation, sans être enregistré.

L'App `Silicium Project Automation` est créée et installée depuis le 25 octobre
2026. Les deux secrets sont provisionnés dans cet environnement. La
réconciliation GitHub `40469270941` a réussi le 27 octobre 2026 : elle a traité
139 issues Workbench, avec 9 changements de statut et 139 mises à jour du champ
`Blocage`. Les 32 éléments `planning-private` restent exclus. La synchronisation
est maintenant active via `SILICIUM_PROJECT_AUTOMATION_ENABLED=1`; les événements
PR/CI et le rapprochement toutes les quinze minutes partagent la même règle.
Le dry-run GitHub de vérification
(`40471477621`) a ensuite traité les 139 issues et prédit zéro changement, après
réconciliation de l'événement CI de #325. Les blocages saisis par un mainteneur
sont conservés ; les résumés `[auto]` sont recalculés. Les journaux ne contiennent
que des compteurs agrégés, car le Project 12 reste privé.

L'observateur de stockage a aussi été vérifié avec un jeton Actions/metadata en
lecture sur les huit dépôts. Aucun job ne crée, modifie ou clôture une issue ;
le workflow ne change que les champs `Status` et `Blocage` du Project.

L'authentification de l'App pour vérifier son installation utilise un JWT
envoyé avec `Authorization: Bearer`, directement en mémoire. Un HTTP 401 ou une
réponse invalide bloque la mesure ; aucun corps de réponse ni jeton n'entre
dans les diagnostics. Le jeton d'installation utilisé pour lire les artefacts
est distinct du JWT et ne reçoit que les permissions Actions nécessaires.

Les workflows natifs qui ajoutent les issues et leurs relations sont conservés.
Ne les retirer qu'après vérification que les nouveaux éléments et relations
continuent d'apparaître dans le Project.

## Budget et preuves

Conserver les limites de dépenses GitHub à zéro. Le contrôle de budget doit
avoir une vue Actions en lecture sur tous les dépôts de l'organisation ; un
jeton limité à Workbench ne prouve pas l'usage global. Le plafond cible des
artefacts temporaires est de 400 Mio. Un défaut de mesure ou de quota reste
bloquant. Aucun runner VPS ne sert de solution de secours.

Les validations de `main` et la publication partagent un groupe de concurrence.
Une exécution en cours va à son terme ; GitHub peut remplacer une exécution
encore en attente par la suivante. Chaque contrôle mesure de nouveau le quota :
une mesure précédente n'est pas une réservation de stockage auprès de GitHub.
Les entrées d'upload sont bornées et une insuffisance de place bloque le run.
Les plans et rapports du contrôle final sont regroupés dans `qualification.json`,
inclus au manifeste signé et à la release. Les artefacts temporaires ne sont
supprimés qu'après confirmation des digests des fichiers publiés.

Les validations Linux/Windows, installations APT/DNF/NSIS, canari et rollback
doivent être joints à la PR avant activation finale. Les tests avec API simulée
ne remplacent pas ces preuves d'intégration.
