# Activation contrôlée de la nouvelle livraison

## État actuel

Fusion est public depuis le 25 octobre 2026, après validation du rapport
d'exposition par le propriétaire. La qualification CI est réactivée avec les
protections publiques. Les workflows de publication, déploiement et suivi
restent désactivés pendant leur préparation. La
publication/diffusion exige en plus `SILICIUM_DELIVERY_ENABLED=1`. Leur présence
ne constitue pas une preuve de livraison. Le protocole de drainage des workers
reste à qualifier ; le programme d'application bloque un changement d'image
réseau plutôt que de tuer une tâche active.

Le premier report d'ouverture a été levé par le propriétaire après validation
des historiques, échanges et droits de publication des visuels. Les plafonds
restent à zéro et les runners du VPS restent retirés. Les suites restent aussi
exécutables localement. La procédure privée ci-dessous est conservée pour un
dépôt privé ; elle ne s'applique plus à la qualification publique de Fusion.

## Qualification ponctuelle d'un dépôt privé

```sh
./dev ci authorize-private --head SHA --minutes 180 --json
./dev ci authorize-private --head SHA --minutes 180 --apply
```

Le SHA doit être celui du checkout propre qui va être poussé dans la PR.
La commande vérifie par l'API de facturation un budget Actions **0, avec arrêt
automatique** et contrôle l'usage réel des artefacts sur toute l'organisation.
Elle conserve la configuration précédente dans `.artifacts/admin`, désactive
les anciens workflows, limite les actions autorisées et ouvre une fenêtre
administrateur réservée à ce SHA (quatre heures au maximum). Aucune clé de
déploiement ni d'App ne passe dans la qualification.

Le workflow n'accepte que les PR internes de l'équipe. Il sépare les contrôles
rapides des quatre validations lourdes simultanées ; une suite manquante reste
un échec du contrôle final. Les caches et uploads de binaires sont désactivés
pendant cette qualification privée ; seuls le plan et les petits rapports
expirant après un jour sont transférés. Un quota GitHub épuisé bloque le run.

La présence du budget à zéro protège les dépenses ; elle ne garantit pas que
GitHub acceptera d'allouer un runner. Le run
[40199389136](https://github.com/Silicium-Project/Fusion/actions/runs/40199389136)
a été refusé avant toute étape, avec un message relatif à la facturation ou
à la limite de dépenses. `dev ci inspect --run ID --json` lit ces annotations
et les distingue d'un test exécuté en échec. Ne pas augmenter le plafond,
ouvrir le dépôt ou relancer en boucle pour contourner ce refus. La cause
précise exige la lecture de l'état de facturation et du quota du compte.

Une qualification PR n'est pas un push `main` qualifié et n'autorise aucune
publication. Après collecte des résultats, supprimer `SILICIUM_PRIVATE_CI_WINDOW`
et suspendre de nouveau Actions jusqu'à la prochaine fenêtre revue. Ne jamais
réactiver les workflows des trois dépôts sources ou les runners VPS.

## GitHub et droits

1. Valider le rapport d'exposition avant l'ouverture publique.
2. Suspendre Actions, vérifier l'absence de jobs VPS actifs, puis désenregistrer
   les runners des quatre dépôts. Ne pas interrompre leurs services applicatifs.
3. Après ouverture : protéger `main`, imposer les PR, `ci/required` lié à GitHub
   Actions, la branche à jour et la résolution des conversations, administrateurs
   compris. Le mode mainteneur unique n'impose aucune approbation externe ;
   CODEOWNERS indique les responsables et la révocation des anciennes approbations
   reste activée. Exiger l'approbation des workflows de tous les contributeurs
   externes et ne pas les approuver pendant la stabilisation.
4. Restreindre les environnements à `main`. `production` et
   `signing-production` exigent une approbation humaine indépendante.
5. Migrer les secrets de déploiement actuellement au niveau dépôt vers les
   environnements protégés. Retirer les anciens droits d'écriture et clés de
   synchronisation des parcours désormais inutiles.

L'organisation transmet actuellement un droit d'écriture par défaut. L'audit
des membres et l'attribution nominative doivent précéder une éventuelle
modification de ce défaut, qui affecterait aussi les autres dépôts.

### Mode mainteneur unique

Ce mode remplace l'exigence initiale de revue indépendante, avec l'accord
explicite du propriétaire le 25 octobre 2026. `main` conserve une protection
de PR avec zéro approbation exigée ; ne pas supprimer cette protection entière.
Les options imposant une revue CODEOWNERS ou une approbation du dernier push
sont désactivées. Les conversations, la CI stricte liée à l'App GitHub Actions,
l'application aux administrateurs et l'interdiction des pushes forcés et des
suppressions restent actives. Aucun nouveau droit de contournement n'est créé.

Vérifier aussi `repos/Silicium-Project/Fusion/rules/branches/main` : les règles
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

La création d'une App requiert la session GitHub d'un propriétaire : le jeton
CLI ne permet pas de la créer via REST. Placer `PROJECT_APP_CLIENT_ID` et
`PROJECT_APP_PRIVATE_KEY` dans `project-automation`, puis vérifier une exécution
sans `--apply` avant de définir `SILICIUM_PROJECT_AUTOMATION_ENABLED=1`.

L'App `Silicium Project Automation` est créée et installée depuis le 25 octobre
2026. Les deux secrets sont provisionnés dans cet environnement. La
réconciliation locale en lecture seule du 27 octobre 2026 a observé 139 éléments
et prédit huit transitions d'état et 139 mises à jour du champ `Blocage` ; elle
n'a effectué aucune écriture. Le résultat intègre les PR qui référencent leurs
issues avec `Refs:`. Le workflow est dans `main`, mais
`SILICIUM_PROJECT_AUTOMATION_ENABLED` n'est pas configuré et l'automatisation
reste donc désactivée. Les blocages saisis par un mainteneur sont conservés,
tandis que les résumés `[auto]` sont recalculés ; les trois anciens messages
standard sont retirés pendant cette migration. Ce
dry-run local ne remplace pas un dry-run du workflow avec l'App. Avant toute
application, qualifier cette PR, inspecter le résultat agrégé du workflow en
lecture seule, puis garder l'activation désactivée jusqu'à décision explicite.
Les exécutions `--apply` journalisent des compteurs agrégés, même en cas
d'erreur ; les détails par issue et les messages d'API sont masqués dans les
logs publics, car les champs du Project 12 restent privés.

L'observateur de stockage a aussi été vérifié avec un jeton Actions/metadata en
lecture sur les huit dépôts. L'activation du workflow reste conditionnée à une
PR qualifiée et à une première réconciliation contrôlée.

L'authentification de l'App pour vérifier son installation utilise un JWT
envoyé avec `Authorization: Bearer`, directement en mémoire. Un HTTP 401 ou une
réponse invalide bloque la mesure ; aucun corps de réponse ni jeton n'entre
dans les diagnostics. Le jeton d'installation utilisé pour lire les artefacts
est distinct du JWT et ne reçoit que les permissions Actions nécessaires.

Ne retirer les anciens workflows natifs qui clôturent ou déplacent une issue
sur une fusion qu'après qualification de la nouvelle réconciliation. Conserver
l'ajout automatique et les relations parent/enfant. Tester une réconciliation
et un événement dupliqué.

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
