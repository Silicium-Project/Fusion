# Décisions d'automatisation CI/CD

Décidées le 30 octobre 2026 pour automatiser au maximum sans affaiblir la
sécurité ni rendre la chaîne plus difficile à maintenir. Chaque décision donne sa
raison et ce qui la remettrait en cause. Elles complètent
[la procédure multi-dépôts](multi-repo-ci.md) et
[l'ordre de fusion](alignment-merge-order.md) ; elles ne remplacent aucun
invariant d'`AGENTS.md`.

## Principe

Automatiser ce qui est déterministe, vérifiable et réversible : planification,
validation, ouverture de PR, relevés de preuves. Laisser à un humain ce qui
engage une identité, un secret, une dépense ou la production. Une automatisation
qui exigerait un jeton d'écriture inter-dépôts ou un secret de plus n'est pas
retenue.

## Décisions

### D1. La politique reste épinglée par SHA complet

Les composants appellent `component-ci.yml` au SHA complet d'un `main` Workbench.
Un tag ou une branche mobile permettrait de changer la CI de cinq dépôts privés
sans PR. Le coût est un repin à chaque changement de politique.

**Réduction du coût.** Grouper les changements de `tools/` et de
`component-ci.yml` avant de repinner. Le repin lui-même est automatisé par
`node tools/ci/repin-policy.mjs --sha SHA [--apply]` : il vérifie que le SHA est
dans `main` de Workbench et que sa preuve de stockage a moins de 15 minutes,
remplace le SHA aux deux endroits attendus et ouvre une PR par composant. Il ne
fusionne rien, ne touche ni gitlink ni `components.lock.json`, et refuse un
workflow dont le format a changé. Sans `--apply`, il ne fait que décrire.

À remettre en cause : si GitHub offre un jeton inter-dépôts à portée minimale et
sans clé longue durée, un repin automatique deviendrait envisageable.

### D2. Un humain fusionne, la machine prépare

Les rulesets privés sont actifs (PR, `qualify / ci/required` strict, merge commit,
discussions résolues, aucune approbation imposée). Chaque fusion reste un acte
humain : c'est la seule barrière contre un code non relu. L'outillage ouvre les
PR, relance les preuves et lit les résultats.

### D3. Les pins ne changent que par `dev workspace pin`

Les gitlinks et `components.lock.json` bougent ensemble, dans une PR, après la
fusion des PR natives. Aucun workflow ne les modifie. C'est ce qui rend un
`main` de Workbench reproductible.

### D4. La preuve de stockage est une garde, pas une barrière de coût

- PR et Integration : preuve de moins de 15 minutes sur le SHA exact.
- Push sur `main` d'un composant : moins de 60 minutes, car la PR a déjà passé la
  garde de 15 minutes. Un `main` rouge pour une preuve périmée masque les vraies
  erreurs.
- Plafond d'organisation : lu dans `organization.plan` ; si le jeton ne le voit
  pas, `SILICIUM_ORG_ARTIFACT_LIMIT_MIB` (400 à 512). Toute autre valeur retombe
  sur 400 Mio.

Cette garde ne limite pas la facturation. Pendant l'essai Enterprise, le
compteur de minutes se relève à la main avant chaque campagne.

### D5. Les retries sont limités aux téléchargements

Les outils épinglés (Anchor, Solana, AppImage, outils de sécurité) se
téléchargent avec trois tentatives au plus, pour une coupure réseau ou un
HTTP 408, 429 ou 5xx. Un écart de SHA-256 n'est jamais retenté. **Aucun test
n'est relancé automatiquement** : un échec fonctionnel se corrige, sinon la CI
ne prouve plus rien.

### D6. Un test instable devient une issue, pas un contournement

On ne désactive pas un test, on ne rallonge pas un délai et on n'ajoute pas de
relance pour obtenir un run vert. Le test instable est documenté dans une issue
du dépôt concerné avec ses journaux, et la qualification de sa suite est
considérée comme non fiable tant qu'elle n'est pas close. Exemple en cours :
l'e2e `raytracer-2` de Network.

### D7. La qualification Integration reste une décision bornée

Un seul run complet à la fois, sur un SHA Workbench figé, après relevé du
solde de minutes (Windows coûte davantage que Linux). Le flag
`SILICIUM_INTEGRATION_ENABLED` s'ouvre pour ce run et se referme ensuite. Aucun
déclenchement planifié tant que le plafond de dépense n'est pas imposé par
GitHub. À remettre en cause : budget d'arrêt disponible ou forfait payant
choisi.

### D8. Rien ne signe, publie ou déploie sans clé fournie par un humain

Signature, publication, déploiement et production exigent des clés, une App
Publisher, des secrets SSH et la décision CI-10. L'automatisation les consomme
quand ils existent ; elle ne les crée pas et ne les copie jamais dans Workbench.

### D9. Les secrets et accès se retirent après leur dernier consommateur

Un secret ou une App sans consommateur est une surface d'attaque, mais « aucun
workflow de `main` ne le lit » ne prouve pas qu'il est inutile. Au 30 octobre
2026, la branche `dev` de Workbench garde les anciens workflows de déploiement
par VPS (`deploy-dev-vps`, `deploy-vps`, `rollback-vps`, `release-dev`,
`reclaim-runner`, `build`, `sync-submodules`, `mirror-epitech`). Ils lisent les
secrets `VPS_*`, `SILICIUM_DEPLOY_APP_*`, `SILICIUM_SYNC_*` et
`SILICIUM_WINDOWS_CERTIFICATE_*`, ainsi que la variable
`SILICIUM_WINDOWS_ALLOW_SELF_SIGNED`. Le dernier déploiement par cette voie date
du 24 octobre. Tant que la chaîne de livraison privée n'a pas déployé en dev et
rejoué un rollback, ces éléments restent le seul chemin vers le VPS en service.

Ordre de retrait :

1. Qualifier le déploiement dev et le rollback de la nouvelle chaîne (CI-10).
2. Retirer les workflows de la branche `dev` (ou la branche elle-même).
3. Vérifier qu'aucun run récent ni aucune procédure manuelle ne lit un secret.
4. Seulement alors, supprimer les secrets de dépôt, la variable et l'App
   `silicium-vps-deployer`, en conservant d'abord ailleurs toute clé à garder :
   un secret GitHub ne se relit pas.

Sans consommateur identifié aujourd'hui : les clés de miroir des dépôts
composants, les Apps de lecture d'Integration et de preuves CI (la doc dit
qu'elles ne sont pas utilisées). Le retrait reste une action d'un propriétaire
de l'organisation, après la même vérification. La double authentification doit
être exigée. Le compte utilisé par l'agent n'a pas le droit `admin` sur les
dépôts.

### D10. Un seul chemin de dépendances

Les mises à jour d'actions passent par `tools/config/actions.json` et ses tests.
Un robot de mise à jour ne les modifie pas ailleurs : il créerait des PR qui
échouent aux tests de registre. À remettre en cause : un format de registre que
l'outil sait lire.

## Revue

Réviser ces décisions à chaque fin d'essai Enterprise, à chaque ajout de
composant, et après tout incident de CI sur `main`. Une décision remplacée est
datée ici avec sa raison.
