# Qualification, publication et déploiement

## Identité d'une livraison

Un candidat est défini par son SHA source, sa version unique, son canal, ses
composants et leurs digests. Le manifeste contient les références de
qualification et les signatures. Une image déployée est désignée par digest.
Deux contenus différents ne peuvent pas partager une version de paquet.

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
  #4 propose aussi des artefacts de compilation bornés et un appel au vérificateur
  Workbench ; elle est encore en brouillon et aucun run n'a été effectué. Elle
  ne construit pas encore un paquet candidat, ne transfère rien vers Workbench,
  et n'appelle pas la livraison.
- `Workbench/.github/workflows/release.yml` écoute les fins du workflow `CI`
  de Workbench, puis exige dans son job `prepare` que le run appartienne au
  dépôt privé `Integration`. Un run public Workbench ne peut donc pas satisfaire
  cette condition. Le run 40359464116 a terminé `skipped` ; ce n'est pas une
  qualification ni une release.
- Le script de candidat actuel vérifie les runs et les artefacts dans
  `Silicium-Project/Workbench`. Il ne consomme pas encore la preuve privée
  `integration/required` ni ses cinq pins.
- `SILICIUM_DELIVERY_ENABLED` est à `0` dans Workbench et
  `SILICIUM_INTEGRATION_ENABLED` n'est pas activé dans Integration. Aucun
  déploiement dev ou prod n'est autorisé par cet état. Le budget privé Actions
  avait été épuisé lors de la dernière vérification du 26 octobre ; il doit être
  vérifié de nouveau avant tout run, sans dépassement facturé ni runner VPS.
- Le marqueur `SILICIUM_DELIVERY_CONTRACT=private-integration-v1` n'est pas
  configuré. Le CLI et les jobs GitHub exigent à la fois ce marqueur et le
  drapeau d'activation ; leur absence bloque aujourd'hui le dispatch. Ces deux
  valeurs sont des verrous d'activation, pas une preuve de qualification. La
  PR #332 ajoute un workflow réutilisable qui vérifie le run privé, le SHA de
  politique, les cinq pins, les rapports et les quatre artefacts de compilation
  exacts avec leurs digests. Elle doit encore être fusionnée et appelée depuis
  Integration ; aucun run privé n'a validé ce raccordement. Le reçu temporaire
  n'est pas signé et ne qualifie pas une livraison.
- Les environnements Workbench de signature et de déploiement n'ont aucun
  secret ni variable d'environnement configuré. Les workflows attendent entre
  autres des clés de signature et `DEPLOY_SSH_HOST` / `DEPLOY_SSH_KNOWN_HOSTS` /
  `DEPLOY_SSH_KEY`; ils ne sont pas configurés. Les environnements Windows de
  signature sont également vides. Ne pas remplacer ces identités dédiées par
  les secrets `VPS_*` d'autres automatismes.
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

Avant d'implémenter l'appel, fixer la destination de chaque sortie (rapport
privé, artefact temporaire, image, paquet, manifeste signé) et vérifier que
les binaires ne révèlent pas une source privée non autorisée à la publication.
Un transfert public ou un jeton d'App plus puissant ne doit pas être choisi
implicitement.

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
