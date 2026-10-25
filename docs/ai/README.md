# Procédures directement utilisables par les agents

Commencer par [AGENTS.md](../../AGENTS.md), puis consulter le fichier homonyme
du composant. `./dev capabilities --json` est l'interface de découverte ;
`./dev doctor` vérifie les prérequis. Aucun plugin ni serveur MCP n'est requis.

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

Pour un service : préparer `dev ops diagnose --environment dev --json`, puis
utiliser `--apply` si l'automatisation est configurée et autorisée. Lire
[les observations et leurs limites](../operations/diagnostics.md). Une absence
de télémétrie ne signifie jamais que les workers sont inactifs.

## Modifier un contrat

Identifier producteur, consommateurs, version et fixtures dans `contracts`.
Qualifier les deux côtés et la compatibilité avec les données existantes.
Pour Solana : garder ID de programme, autorités et clés hors du changement
sauf demande explicite distincte ; localnet est l'oracle de CI.

## Publier et déployer

Lire [le runbook](../operations/delivery.md). Utiliser un SHA exact, le canal
explicite et le manifeste qualifié. Préparer avec `dev release plan` et
`dev deploy request`. L'option `--apply` demande l'action GitHub ; elle ne
permet pas de contourner les protections ou l'approbation production.

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
