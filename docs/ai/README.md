# Procédures directement utilisables par les agents

Commencer par [AGENTS.md](../../AGENTS.md), puis consulter le fichier homonyme
du composant. `./dev capabilities --json` est l'interface de découverte ;
`./dev doctor` vérifie les prérequis. Aucun plugin ni serveur MCP n'est requis.

## Choisir le bon dépôt

Lire [la composition Workbench](../architecture/multi-repo.md). Les applications
sont des sous-modules de dépôts privés, pas des dossiers publics à réintroduire
dans Git. `dev workspace status --json` décrit les pins et checkouts ;
`dev workspace init --component ID --apply` récupère une source autorisée.
Dans un clone natif, définir `SILICIUM_WORKBENCH` vers un checkout propre de la
politique et utiliser son lanceur `dev`. Sa qualification crée une composition
temporaire dont les rapports enregistrent le SHA source et celui de la politique.
Ne jamais pousser ce commit synthétique de qualification.

La CI publique `--scope public` ne qualifie pas les applications. La qualification
privée `--scope integration` doit couvrir les cinq pins avant livraison. Un
quota privé épuisé reste un blocage. Lire `deferred_suites` et rapporter toutes
les validations manquantes. Mettre à jour les deux pins ensemble avec
`dev workspace pin --component ID --revision SHA --apply`, puis créer une PR
Workbench liée aux PR natives.

## Implémenter une tranche

1. Lire l'issue, son parent, ses dépendances et la cible de validation du Project.
2. Ne démarrer que si préparation, responsable, taille et prérequis sont définis.
3. Créer une branche courte et une PR brouillon avec les URL des issues.
4. Lire les contrats affectés ; demander au plan CI les suites nécessaires.
5. Implémenter le changement avec le contre-exemple et les tests applicables.
   Appliquer `dev format --write` puis les [normes de qualité](../development/quality.md).
6. Exécuter les suites communes et conserver leurs rapports. Ne pas inventer
   un résultat manquant ni retirer un contrôle pour obtenir une CI verte.
7. Mettre à jour documentation, exemples et instructions locales.
8. Présenter les changements, résultats observés et limites ; laisser la
   décision de revue/acceptation à un humain autorisé.

La synchronisation du Project 12 observe aussi les PR et checks du dépôt privé
Integration, avec un délai maximal nominal de quinze minutes. Les logs publics
ne contiennent que des totaux ; un PR privé sans gate requis unique reste en
attente. Ne saisis pas toi-même un statut comme preuve d'acceptation.

### Faire intégrer une PR

Le mode mainteneur unique autorise le mainteneur à examiner sa propre PR.
Vérifier le SHA courant, `ci/required`, la mise à jour avec `main` et les
discussions résolues, puis présenter les preuves pour sa décision de fusion.
Une revue externe est facultative ; ne pas fabriquer une approbation via un
bot ou un autre compte. L'accord pour changer les règles ne vaut pas accord
pour fusionner une PR. Conserver les merges d'historiques de la migration.

Pour une issue, `dev issue accept` demande toujours une autorisation humaine
explicite, la checklist complète et la preuve de la cible sur `main`. Il vérifie
que les PR ont été fusionnées par un humain ayant les droits d'écriture et
enregistre les SHA et ce compte. Ne pas ajouter `--human-approved` de sa propre
initiative. La production conserve ses approbations indépendantes.

## Diagnostiquer une CI

Lire le run exact avec `dev ci inspect --run ID`. Comparer SHA, suite, plan,
rapport et environnement. Corriger l'erreur d'infrastructure ou l'oracle
fonctionnel identifié. Une relance d'erreur fonctionnelle ne remplace pas une
correction. Une nouvelle révision invalide les anciens résultats applicables.

Si aucun runner n'a démarré, lire `diagnostics` : un refus de facturation ou
de limite de dépenses ne dit rien du résultat des tests. Conserver le plafond
à zéro, la visibilité décidée et les échecs visibles ; aucune relance répétée
ni repli sur un runner VPS n'est autorisé.

`dev ci metrics --limit 20 --json` donne les distributions et le nombre
d'observations. Vérifier le SHA des runs avant de comparer ; ne pas présenter
une absence de rapport ou un cache désactivé comme un gain de performance.
Le téléchargement des rapports est borné à 64 Mio au total ; consulter
`runs_skipped_for_download_budget` avant d'interpréter les métriques de cache.
Lire séparément `workflow_start_wait` (création du run jusqu'au démarrage du
workflow) et `job_queue_and_matrix_wait` (création du job jusqu'à sa première
étape). Si le premier est élevé et le second bas, l'attente précède les jobs ;
les métadonnées seules ne prouvent pas sa cause. Pour les artefacts, ne présenter
`bytes` comme total que si `complete` vaut `true` ; sinon `bytes_observed` n'est
qu'un sous-total.

Pour un service : préparer `dev ops diagnose --environment dev --json`, puis
utiliser `--apply` si l'automatisation est configurée et autorisée. Lire
[les observations et leurs limites](../operations/diagnostics.md). Une absence
de télémétrie ne signifie jamais que les workers sont inactifs.

## Modifier un contrat

Identifier producteur, consommateurs, version et fixtures dans `contracts`.
Qualifier les deux côtés et la compatibilité avec les données existantes.
Pour Solana : garder ID de programme, autorités et clés hors du changement
sauf demande explicite distincte ; localnet est l'oracle de CI.

Avant d’affirmer qu’un résultat P2P ou Solana est vérifié, final, indépendant
du site ou sûr pendant une partition, lire [les frontières de confiance et les
états de finalité](../architecture/trust-boundaries.md). Ce document sépare les
observations aux SHA étudiés des invariants visés et liste les limites encore
ouvertes ; ne pas présenter une signature, un hash, une copie locale ou un vote
comme preuve plus forte que son contrat.

## Qualification privée

Lire [le runbook multi-dépôts](../operations/multi-repo-ci.md). Les workflows
natifs et Integration restent suspendus tant que leurs PR, flags et quota ne
sont pas prêts. Ne pas contourner ce blocage. Les protections privées Free
ne doivent pas être décrites comme équivalentes aux protections publiques.
Les preuves d’acceptation inter-dépôts et le transport privé des artefacts
restent à qualifier ; ne pas accepter une fonctionnalité sur le seul gate public.

## Publier et déployer

Lire [le runbook](../operations/delivery.md). Utiliser un SHA exact, le canal
explicite et le manifeste qualifié. `dev release plan` distingue maintenant
le succès public Workbench de la qualification privée requise ; il ne marque
pas le public comme livraison qualifiée. C'est une commande de
préparation. Au 27 octobre 2026, le raccordement de la qualification privée à la
release et au déploiement n'est pas opérationnel (issue
[CI-10](https://github.com/Silicium-Project/Workbench/issues/331)). Ne lance
pas `dev deploy request --apply`, ne change pas les variables de livraison et
ne traite pas une CI publique verte comme qualification des cinq dépôts. Les
tests privés restent suspendus tant que quota et plafond à zéro ne sont pas
vérifiés. Après acceptation de CI-10, l'option `--apply` demandera l'action
GitHub autorisée ; elle ne contournera pas les protections ni l'approbation
production.

## Utiliser les fonctions produit existantes

Lire [les parcours détaillés et leurs diagnostics](product-usage.md) pour les
commandes, droits, effets, erreurs et validations associés.

- Site en développement : accès VPN et CA de l'équipe ; aucune désactivation
  permanente de TLS pour contourner un certificat non approuvé.
- Machines : installer via les dépôts APT/DNF de `/download`, puis associer le
  PC au compte par le parcours existant. Les clés restent dans leur stockage.
- Calculs : utiliser les parcours `/jobs` et les contrats de l'API ; vérifier
  les états réellement renvoyés, les résultats et les preuves disponibles.
- Paiements : distinguer localnet/Devnet, SIL et SOL ; utiliser les autorisations
  du compte et ne pas présenter une simulation comme un paiement confirmé.

Les exemples authentifiés utilisent des variables locales, jamais des clés ou
jetons réels dans Git. Consulter les README des composants pour les endpoints
et fixtures. Les fonctionnalités prévues dans la roadmap restent des travaux
à réaliser tant que leur contrat et leur preuve de livraison sont absents.
