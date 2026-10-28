# Qualification, publication et déploiement

## Identité d'une livraison

Un candidat est défini par son SHA source, sa version unique, son canal, ses
composants et leurs digests. Le manifeste contient les références de
qualification et les signatures. Une image déployée est désignée par digest.
Deux contenus différents ne peuvent pas partager une version de paquet.

Les manifestes récupérés depuis une release sont des entrées non fiables :
le validateur vérifie d'abord que le document et ses structures imbriquées sont
des objets/listes JSON de la forme attendue. Une forme malformée est refusée
comme identité invalide avant toute utilisation. Cette validation de structure
ne remplace jamais la vérification de la signature détachée avec le trust anchor.
Le tag d'une release doit aussi correspondre à son indicateur GitHub
`prerelease` pour le canal préparé ; une incohérence bloque la sélection de la
baseline au lieu de laisser la release hors du contrôle de version.
Avant publication et déploiement, le répertoire doit contenir exactement les
assets déclarés, avec leurs tailles et SHA-256 concordants ; les fichiers de
manifeste et de signature sont des fichiers réguliers non vides. La signature
GPG est vérifiée séparément avec le trust anchor.

Les artefacts temporaires de qualification et de livraison portent le numéro
de tentative du workflow qui les a produits. Les téléchargements, la preuve
permanente et le nettoyage sélectionnent cette tentative exacte afin qu'une
relance ne récupère ni ne supprime les sorties d'une ancienne tentative.

Les formats APT/RPM utilisent `~dev.N` pour conserver l'ordre des versions ;
les versions stables suivent les préversions. Le compteur Windows est borné
et vérifié. Les identifiants Tauri et les chemins de données restent stables.

Les compteurs Windows 1 à 65534 servent aux versions dev ; 65535 est réservé
à la stable. Une publication doit être strictement plus récente que le candidat
signé précédent du canal, et son source doit en descendre.

## État vérifié au 27 octobre 2026

La chaîne décrite ci-dessous est la **cible** ; elle n'est pas encore
opérationnelle après la séparation de Workbench et des cinq dépôts privés.

- `Integration` dispose d'une qualification privée manuelle. La PR Integration
  #4 propose les quatre artefacts de compilation bornés, le préflight privé et
  la signature détachée du reçu ; elle reste en brouillon et aucun run privé
  n'a été effectué.
- Le récepteur Workbench qui téléchargeait les sorties privées depuis Integration
  a été retiré. La politique réutilisable Workbench ne reçoit que le plan, les
  rapports et un reçu limité aux métadonnées. Le staging des sorties privées
  appartient à un workflow Integration protégé ; elles ne transitent pas par
  un runner public.
- La PR Integration #4 ajoute le préflight `workflow_run`, fermé par défaut.
  Après une qualification manuelle réussie, Integration signe le reçu exact
  avec Ed25519. Le préflight vérifie cette signature et lie le reçu à
  l'événement avant de télécharger les quatre sorties depuis le dépôt privé ;
  il revérifie IDs, digests et tailles avec la politique Workbench, puis
  matérialise les cinq pins avec le Source Reader. Le code reste en brouillon,
  son verrou `SILICIUM_DELIVERY_PREFLIGHT_ENABLED` est absent et aucun run
  n'a été lancé.
- Son brouillon contient aussi des jobs Linux et Windows qui revalident
  l'identité candidate, consomment seulement les sorties qualifiées utiles et
  construisent des installateurs non signés. Ils sont fermés par défaut par
  `SILICIUM_CANDIDATE_BUILD_ENABLED`, bornés à 120/40 Mio et retenus un jour.
  Ils ne signent, publient ou déploient rien ; ils ne sont pas encore fusionnés
  ni exécutés. Le nouveau validateur Workbench doit d'abord être intégré à
  `main` avec la PR #332.
- Les scripts `prepare-private` et de staging lient un candidat aux IDs/digests
  de la qualification, au SHA Workbench et aux cinq pins. La signature des
  dépôts, la validation complète d'installation, la publication immuable et le
  déploiement restent à raccorder dans Integration ; aucun candidat n'est livré.
- `SILICIUM_DELIVERY_ENABLED=0` dans Workbench et son marqueur de contrat est
  absent. Dans Integration, `SILICIUM_INTEGRATION_ENABLED`,
  `SILICIUM_DELIVERY_PREFLIGHT_ENABLED`, `SILICIUM_CANDIDATE_BUILD_ENABLED` et
  le marqueur de contrat sont absents.
  Aucun run privé, préflight, déploiement dev ou déploiement prod n'est
  autorisé par cet état. Le budget privé Actions était épuisé lors de la
  vérification du 26 octobre ; il faut vérifier le solde avant tout run, sans
  dépassement facturé ni runner VPS.
- L'App Source Reader est installée uniquement sur les cinq dépôts privés et ses
  deux secrets chiffrés existent dans Integration. Elle garde `contents: read`
  seulement ; elle ne télécharge pas les artefacts et ne publie rien.
- Aucun App Publisher n'est installé. Le Source Reader ne doit pas recevoir de
  permissions d'écriture pour le remplacer.
- Le marqueur `SILICIUM_DELIVERY_CONTRACT=private-integration-v1` n'est pas
  configuré. Le CLI et les jobs GitHub exigent à la fois ce marqueur et le
  drapeau d'activation ; leur absence bloque aujourd'hui le dispatch. Ces deux
  valeurs sont des verrous d'activation, pas une preuve de qualification. La
  PR #332 ajoute un workflow réutilisable et un vérificateur de réception qui
  vérifient le run privé, le SHA de politique, l'inclusion de cette politique
  dans le SHA source qualifié, les cinq pins, les rapports et les quatre
  artefacts de compilation exacts avec leurs digests. Elle ajoute aussi la
  vérification Ed25519 du reçu privé. Le commit contenant ces changements doit
  être intégré à `Workbench/main`, puis épinglé depuis Integration avant toute
  qualification privée ; aucun run privé n'a validé le raccordement.
- La clé privée Ed25519 du reçu est un secret Integration, injecté seulement
  dans le job `integration/sign-evidence`. La clé publique versionnée est le
  trust anchor des deux dépôts. Les attestations natives sont disponibles pour
  les dépôts privés Enterprise ([documentation GitHub](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)), mais le workflow actuel ne les émet ni ne les
  vérifie. Les attestations privées GitHub ne publient pas dans le journal de
  transparence public. Conserver le reçu Ed25519 jusqu'à ce qu'une migration
  soit implémentée, vérifiée par des tests négatifs et acceptée ; l'accès en
  écriture à Integration reste la frontière de confiance actuelle. Une rotation
  de la clé Ed25519 exige de remplacer le secret et les deux clés publiques
  ensemble.
- Les environnements Workbench de signature et de déploiement n'ont aucun
  secret configuré. Les fingerprints APT/RPM sont présents dans les contrats,
  mais les clés privées APT/RPM/release et le trust anchor public release sont
  absents. Les secrets SSH dédiés aux environnements `development` et
  `production` sont également absents. Les environnements Windows de signature
  sont vides. Ne pas remplacer ces identités par les secrets `VPS_*` d'autres
  automatismes.
- L'environnement de production possède une règle de réviseurs, mais cela ne
  prouve pas que la chaîne privée de qualification appelle cet environnement.

Le raccordement est suivi dans [CI-10](https://github.com/Silicium-Project/Workbench/issues/331).
Ne pas lancer `dev deploy request --apply`, ne pas activer les variables de
livraison et ne pas considérer un run public vert ou le reçu temporaire comme
preuve de publication ou de déploiement privés tant que cette issue n'est pas
acceptée.

### Frontière entre dépôts

La qualification doit rester exécutée dans Integration, où les sources et
rapports privés sont protégés. Le futur appel de livraison doit relier le SHA
Workbench exact, les cinq SHAs de `components.lock.json`, le run privé et les
rapports réussis. Un workflow réutilisable public appelé depuis Integration
hérite du contexte et des permissions du dépôt appelant ; son `GITHUB_TOKEN`
ne gagne pas de droits d'écriture dans Workbench. Le contrat doit donc séparer
les droits de lecture des sources, de publication, de signature et de
déploiement, et passer explicitement uniquement les secrets requis. `secrets:
inherit` et l'App Source Reader en écriture sont interdits.

Les rapports, reçus et sorties de compilation restent privés dans Integration.
Seuls les paquets, images ou manifestes explicitement définis comme livrables
publics peuvent quitter ce dépôt. La publication dans Workbench utilisera une
App distincte avec `contents: write`; le droit `Actions: write` est évité en
déclenchant le déploiement protégé par l'événement de publication. GHCR doit
être publié avec le `GITHUB_TOKEN` du dépôt Integration et un accès de paquet
compatible ; une App GitHub n'est pas un substitut au jeton de registre accepté
par GitHub Packages. Aucun de ces chemins n'est activé actuellement.

## Chaîne

Une fois le raccordement CI-10 qualifié, la cible est :

1. CI sur les PR de l'équipe et `main` ; `ci/required` valide les rapports.
2. Construction des candidats après intégration, avec outils verrouillés.
3. Signature et validation des artefacts/index APT/DNF dans un job protégé.
4. Publication du manifeste et des fichiers immuables.
5. Déploiement dev automatique après qualification.
6. Promotion production d'un candidat précis avec approbation humaine.

Les contrôles applicables et exécutés restent consultables dans le run GitHub.
Les artefacts temporaires sont bornés ; les clés, ledgers et configurations
réelles ne vont pas dans les caches. Les quotas épuisés bloquent la livraison.

Les snippets de la page de téléchargement et les tests d'installation ont une
source unique dans `contracts/install`. La suite `package-installation` utilise
Debian 12, Ubuntu 24.04 et Fedora 44. Elle contrôle versions, bibliothèques et
ressources embarquées, puis la conservation d'un fichier de données utilisateur.
Lorsqu'un candidat signé précédent existe, elle l'installe puis exécute le
snippet de mise à niveau vers le nouveau. Au premier candidat, seule
l'installation initiale est qualifiée : cette limite est écrite dans la preuve
`installations.json` publiée avec le manifeste signé.

Les conteneurs utilisent une copie avec deux pointeurs de transport APT/DNF
rebasés en HTTP interne ; les métadonnées signées, clés et paquets sont identiques
à la livraison. Ce parcours ne qualifie pas la CA VPN ni un déploiement du VPS.

## Préparation et application

```sh
./dev release plan --channel dev --version 0.3.0-dev.1 --run ID --json
./dev deploy request --manifest .artifacts/candidate.json --environment dev --json
```

La commande de plan est disponible. Aujourd'hui, `--apply` est refusé par le
CLI tant que le drapeau et le marqueur de contrat privé ne sont pas configurés.
Les secrets et variables de signature/déploiement sont également absents ; ne
contourne pas ce refus en envoyant un dispatch manuel.
Le chemin sera considéré actif après CI-10, la qualification privée complète et
l'activation contrôlée des workflows. La requête devra alors viser un candidat
signé exact ; aucune construction ne sera faite sur le VPS. Les signatures et
empreintes seront vérifiées avant activation.

L'application prépare un répertoire distinct et vérifie les identités de
l'API et du web avant de changer le pointeur de paquets. Le changement d'image
réseau reste bloqué jusqu'à qualification d'un protocole de drainage et de
mise à jour progressive des machines. Une télémétrie absente ne démontre pas
leur disponibilité. Les volumes, identités, wallets et tâches sont conservés.

## Retour arrière

Conserver le candidat précédent et ses fichiers. Revenir par digest et par
snapshot de dépôt de paquets. Vérifier la santé et les versions après reprise.
Les migrations doivent rester compatibles. Un rollback applicatif n'annule
ni une écriture métier déjà validée ni une transaction blockchain.

## Exploitation

Les diagnostics sont des procédures séparées du déploiement. Commencer par
les mesures de santé, versions, espace et ressources en lecture seule. Les
opérations modificatrices ciblent un service ou un candidat explicite.
Le VPS exécute les services et sert les paquets ; les builds/tests de CI
s'exécutent sur GitHub.

Voir [les diagnostics](diagnostics.md), [l'activation contrôlée](bootstrap.md)
et [le miroir Epitech indépendant](epitech-mirror.md). Après l'ouverture publique,
ces workflows restent désactivés jusqu'à leur qualification et leur activation
explicite, avec les clés et accès protégés.
