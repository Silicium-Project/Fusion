# Qualification, publication et déploiement

## Identité d'une livraison

Un candidat est défini par son SHA source, sa version unique, son canal, ses
composants et leurs digests. Le manifeste contient les références de
qualification et les signatures. Une image déployée est désignée par digest.
Deux contenus différents ne peuvent pas partager une version de paquet.

Les formats APT/RPM utilisent `~dev.N` pour conserver l'ordre des versions ;
les versions stables suivent les préversions. Le compteur Windows est borné
et vérifié. Les identifiants Tauri et les chemins de données restent stables.

## Chaîne

1. CI sur les PR de l'équipe et `main` ; `ci/required` valide les rapports.
2. Construction des candidats après intégration, avec outils verrouillés.
3. Signature et validation des artefacts/index APT/DNF dans un job protégé.
4. Publication du manifeste et des fichiers immuables.
5. Déploiement dev automatique après qualification.
6. Promotion production d'un candidat précis avec approbation humaine.

Les contrôles applicables et exécutés restent consultables dans le run GitHub.
Les artefacts temporaires sont bornés ; les clés, ledgers et configurations
réelles ne vont pas dans les caches. Les quotas épuisés bloquent la livraison.

## Préparation et application

```sh
./dev release plan --channel dev --version 0.3.0-dev.1 --run ID --json
./dev deploy request --manifest .artifacts/candidate.json --environment dev --json
```

Examiner le résultat avant d'ajouter `--apply`. Les requêtes passent par le
workflow GitHub `deploy.yml` ; aucune construction n'est faite sur le VPS.
Les signatures et empreintes doivent être vérifiées avant activation.

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
et [le miroir Epitech indépendant](epitech-mirror.md). Le maintien privé décidé
par le propriétaire conserve ces workflows désactivés.
