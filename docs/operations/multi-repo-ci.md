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
5. Conserver ces preuves privées. Les résultats publics de Workbench restent
   des preuves de ses seuls fichiers publics. Ne pas activer une publication
   à partir de ce seul gate.

La qualification native utilise un commit synthétique **local et temporaire**,
parent du SHA Workbench épinglé. Il permet de qualifier une nouvelle version du
composant sans modifier un checkout utilisateur. Les métadonnées enregistrent
les deux SHA originaux. Ce commit n'est ni une version intégrée ni un candidat
livrable ; il ne doit jamais être poussé.

## Activation après migration

Les workflows natifs utilisent `SILICIUM_COMPONENT_CI_ENABLED=1`. Integration
utilise `SILICIUM_INTEGRATION_ENABLED=1`. Les flags restent à zéro pendant la
préparation ; les Actions des anciens composants restent suspendues jusqu'à
l'intégration de leurs nouveaux workflows et la disponibilité du quota privé.
Un workflow suspendu ou ignoré ne constitue jamais une qualification.

Avant un lancement privé, exécuter le workflow CI de Workbench sur `main` et
attendre sa réussite. Le job protégé `budget` observe tous les dépôts avec
l'App existante ; il vérifie la marge de stockage avec une réserve de 210 Mio.
Les workflows privés exigent que cette étape exacte ait réussi depuis moins
de quinze minutes. Il s'agit d'une observation bornée, pas d'un verrou global
de stockage entre tous les dépôts. Les campagnes complètes sont sérialisées,
les rapports limités à 1 Mio et expirent après un jour ; les caches privés
sont désactivés pendant la migration.

Le budget Actions de l'organisation doit rester à zéro avec blocage du
dépassement. Les runners standards des dépôts privés consomment le quota
inclus ; le statut public de Workbench ne change pas cette règle. Son
épuisement bloque la qualification. Ne pas utiliser de runner VPS, copier des
sources privées dans des workflows publics ou ouvrir un budget facturable.

## Accès aux sources

Integration possède une clé de déploiement **en lecture seule par composant**,
sous les secrets `SOURCE_KEY_API`, `SOURCE_KEY_WEB`, `SOURCE_KEY_NODE`,
`SOURCE_KEY_NETWORK` et `SOURCE_KEY_SOLANA`. Aucune clé de wallet, de signature
ou d'upgrade Solana n'est utilisée. Aucune de ces clés n'est configurée dans
Workbench ni dans la CI native.

`materialize.mjs` n'accepte que Integration privé sur `main`. Il vérifie URL,
gitlink et lock, utilise les clés SSH GitHub épinglées, récupère les commits,
puis supprime clés temporaires et variables avant toute commande applicative.
Les clés publiques et leurs identifiants sont inventoriés dans l'espace privé
d'exploitation. Rotation : ajouter une nouvelle clé de lecture au seul dépôt
concerné, remplacer le secret chiffré, vérifier un fetch exact dans le contexte
privé puis révoquer l'ancienne clé. Ne jamais imprimer la clé privée.

GitHub Free ne fournit pas les mêmes protections sur les dépôts privés que sur
Workbench public. Les conventions PR/CODEOWNERS ne sont pas présentées comme
des protections serveur effectives. Les membres autorisés à écrire dans ces
dépôts constituent donc une frontière de confiance ; maintenir des accès
limités et ne pas y approuver de code extérieur pendant la stabilisation.

## Livraison et miroir Epitech

La reprise du transport des artefacts privés vers la signature/publication
reste bloquée avant sa propre qualification. Les anciens workflows publics
`release`, `campaigns` et `mirror-epitech` ne peuvent plus construire ou publier
une composition incomplète. Les flags de livraison restent à zéro.

La qualification privée seule ne démontre pas les signatures, les installations
APT/DNF/Windows, un déploiement, un rollback ni une acceptation d'issue. La
production conserve ses approbations indépendantes et les services existants
ne sont pas modifiés par ce chantier.
