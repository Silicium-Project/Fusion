# Activation contrôlée de la nouvelle livraison

## État actuel

Les workflows sont fournis et désactivés tant que Fusion reste privé. La
publication/diffusion exige en plus `SILICIUM_DELIVERY_ENABLED=1`. Leur présence
ne constitue pas une preuve de livraison. Le protocole de drainage des workers
reste à qualifier ; le programme d'application bloque un changement d'image
réseau plutôt que de tuer une tâche active.

## GitHub et droits

1. Valider le rapport d'exposition avant l'ouverture publique.
2. Suspendre Actions, vérifier l'absence de jobs VPS actifs, puis désenregistrer
   les runners des quatre dépôts. Ne pas interrompre leurs services applicatifs.
3. Après ouverture : protéger `main`, imposer `ci/required`, la revue indépendante,
   CODEOWNERS, la résolution des conversations et la révocation des anciennes
   approbations. Exiger l'approbation des workflows de tous les contributeurs
   externes et ne pas les approuver pendant la stabilisation.
4. Restreindre les environnements à `main`. `production` et
   `signing-production` exigent une approbation humaine indépendante.
5. Migrer les secrets de déploiement actuellement au niveau dépôt vers les
   environnements protégés. Retirer les anciens droits d'écriture et clés de
   synchronisation des parcours désormais inutiles.

L'organisation transmet actuellement un droit d'écriture par défaut. L'audit
des membres et l'attribution nominative doivent précéder une éventuelle
modification de ce défaut, qui affecterait aussi les autres dépôts.

## Signatures et registre

- `signing-development` / `signing-production` : secrets `APT_SIGNING_KEY`,
  `RPM_SIGNING_KEY`, `RELEASE_SIGNING_KEY` ; variables correspondantes
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
code ne lui sont attribués. L'installation vise Fusion et planning-private.

La création d'une App requiert la session GitHub d'un propriétaire : le jeton
CLI ne permet pas de la créer via REST. Placer `PROJECT_APP_CLIENT_ID` et
`PROJECT_APP_PRIVATE_KEY` dans `project-automation`, puis vérifier une exécution
sans `--apply` avant de définir `SILICIUM_PROJECT_AUTOMATION_ENABLED=1`.

Retirer seulement ensuite les anciens workflows natifs qui clôturent ou
déplacent une issue sur une fusion. Conserver l'ajout automatique et les
relations parent/enfant. Tester une réconciliation et un événement dupliqué.

## Budget et preuves

Conserver les limites de dépenses GitHub à zéro. Le contrôle de budget doit
avoir une vue Actions en lecture sur tous les dépôts de l'organisation ; un
jeton limité à Fusion ne prouve pas l'usage global. Le plafond cible des
artefacts temporaires est de 400 Mio. Un défaut de mesure ou de quota reste
bloquant. Aucun runner VPS ne sert de solution de secours.

Les validations Linux/Windows, installations APT/DNF/NSIS, canari et rollback
doivent être joints à la PR avant activation finale. Les tests avec API simulée
ne remplacent pas ces preuves d'intégration.
