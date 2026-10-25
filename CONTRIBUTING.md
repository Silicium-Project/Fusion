# Contribuer à Silicium

## Dépôt concerné

Les sources applicatives sont dans les dépôts privés indiqués dans le
[README](README.md). Les issues publiques restent centralisées dans Workbench ;
une PR native référence leur URL canonique. Une PR Workbench met ensuite à jour
le gitlink et `components.lock.json`. Le gate public valide le dépôt d’intégration ;
la qualification applicative complète est privée et obligatoire avant livraison.

## Parcours

1. Choisir une tranche prête dans le Project 12 ; préparer les prérequis et le
   responsable avant de démarrer. Une tranche active par personne est la règle.
2. Lire [AGENTS.md](AGENTS.md) et [les commandes communes](docs/development/commands.md).
3. Créer `lf-<type>-<issue>-<objet>` depuis `main` à jour et ouvrir une PR brouillon.
4. Référencer les issues par URL dans la section `Refs` du modèle de PR.
5. Décrire les critères d'acceptation, contrats affectés et risques de migration.
6. Exécuter le plan de validation applicable et joindre les résultats réels.
7. Mettre à jour documentation humaine, instructions IA et exemples.
8. Faire examiner les changements et obtenir la décision de fusion du mainteneur ;
   après intégration, qualifier la cible de livraison.

Éviter les mots-clés de clôture automatique : une PR fusionnée place une issue
en validation, elle ne démontre pas seule que son résultat est accepté.

## Revue

Le propriétaire a retenu le mode **mainteneur unique** le 25 octobre 2026.
Une PR, la réussite de `ci/required` sur la révision courante, une branche à jour
et la résolution des discussions restent obligatoires, administrateurs compris.
La revue par un autre compte est facultative. Le mainteneur peut examiner et
fusionner sa propre PR ; la CI et une analyse automatisée ne remplacent pas sa
décision humaine. La fusion ne vaut toujours pas acceptation d'une issue.

Les modifications du protocole, de Solana, des contrats, des secrets et de la
CI doivent être examinées par le propriétaire correspondant, qui peut aussi
être l'auteur. CODEOWNERS indique ces responsabilités sans imposer un second
approbateur. Les protections de production ne changent pas. Les modifications
mécaniques, mises à niveau et évolutions fonctionnelles sont des PR distinctes.
Une validation échouée ou impossible à exécuter reste explicitement visible.

Les commits suivent `type: objet` (`feat`, `fix`, `refactor`, `test`, `docs`,
`ci`, `chore`). L'auteur réel et les contributions restent attribués.

## Contributions externes

Le code peut être consulté et forké. Pendant la stabilisation, l'équipe ne
prend pas en charge les PR externes et n'approuve pas leurs workflows. Les
canaux de signalement de sécurité restent ceux de [Security.md](Security.md).

## Livraison

Les builds et tests tournent sur GitHub. La publication et le déploiement sont
décrits dans [le runbook](docs/operations/delivery.md). Le VPS ne constitue pas
un runner de secours. Les données et clés privées ne vont jamais dans Git,
les caches, les exemples ou les artefacts.
