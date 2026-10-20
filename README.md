# Silicium FrontEnd

Interface Nuxt 3 de Silicium. Le site réunit la présentation publique du réseau,
l'authentification, le pilotage des calculs, l'observation du réseau et la gestion
du compte dans une seule expérience responsive.

## Architecture

- `pages/` définit les vues publiques et privées.
- `layouts/` sépare le site vitrine, l'authentification et l'application.
- `components/` contient les briques d'interface classées par domaine.
- `composables/` porte les parcours métier et l'état partagé.
- `services/` contient le cache mémoire avec durée de vie et déduplication.
- `middleware/` protège les routes authentifiées et invitées.
- `types/` et `utils/` centralisent les contrats et le formatage.
- `assets/css/` contient les tokens, fondations et composants visuels.

La direction visuelle associe un fond perle, du verre discret et des contrôles
en relief. Les actions principales sont bleues. Les statuts conservent leurs
couleurs sémantiques : vert pour une réussite, ambre pour une attente et rouge
pour un échec. Le logo provient du nouveau visuel fourni dans Téléchargements.

## Parcours

- `/`, `/service`, `/blockchain`, `/about`, `/contact` : présentation publique.
- `/auth` : connexion et création de compte.
- `/dashboard` : synthèse du compte et des calculs.
- `/jobs`, `/jobs/new`, `/jobs/:id` : création et suivi d'un calcul.
- « Recherche dans mes documents » : dépôt de documents sur `/jobs/new?workload=documents` (ajout à une recherche existante avec `&collection=…`), puis recherche, ouverture des documents et export de l'index sur `/jobs/:id` (`components/jobs/DocumentSearch.vue`, `utils/documents.ts`).
- `/network`, `/nodes` : capacité agrégée et installation d'un nœud.
- `/workloads` : les types de calcul (but, fonctionnement, entrée attendue) avec un fichier d'exemple chacun, servi depuis `public/examples/`.
- `/profile` : identité, sécurité et portefeuille Solana.

Le client conserve le jeton d'accès pour les appels courts et utilise le jeton
de renouvellement lorsque la session expire. Les données non sensibles sont
mises en cache avec une durée de vie courte ; les opérations d'écriture
invalident les entrées concernées. Les vues privées sont servies avec
`Cache-Control: no-store`.

## Langues

Le site existe en français (par défaut), en anglais et en allemand. Les textes
sont dans `locales/fr.ts` (référence), `locales/en.ts` et `locales/de.ts` :
TypeScript refuse une clé manquante et `tests/i18n.test.ts` vérifie que les
trois catalogues ont la même forme. Dans un composant :
`const { t, tl } = useI18n()`, puis `t('cle', { count })` ou `tl('liste')`.
Le choix (`LocaleSwitcher`) est gardé dans le cookie `silicium_locale` et
envoyé à l'API dans `Accept-Language`, qui répond dans la même langue.

## Saisies

`utils/validation.ts` reprend les règles de l'API (`BackEnd/internal/handler/userInput.go`) :
e-mail, nom d'utilisateur (3 à 30 caractères `A-Z a-z 0-9 . _ -`), prénom et
nom (50 caractères, lettres), mot de passe (8 caractères à 72 octets), nom et
description d'un calcul (120 et 1 000 caractères, sans caractères invisibles).

## Développement

```shell
npm ci
npm run dev
```

Le frontend écoute sur `http://localhost:3001` en développement. Par défaut, l'API est appelée via
le proxy relatif `/api`. Les variables disponibles sont documentées dans
`.env.example`.

## Vérifications

La vitrine présente les quatre types de calcul et affiche les états renvoyés
par le service. Le visuel d'accueil est identifié comme une illustration de
rendu. Sur `/service`, le schéma explique la répartition ; le parcours 3D se
déplie et se charge à la demande. `/workloads#documents` (ou `#raytracer`,
`#sha256`, `#batchAI`) ouvre directement le guide du calcul choisi.

La liste des projets devient une liste de blocs sur mobile. Le tableau de bord
emploie une présentation compacte des projets récents. Les champs de mot de
passe partagent `UiPasswordInput`, avec une action afficher/masquer. Le choix de
langue reste disponible sur petit écran dans un sélecteur natif.

La page `/download` regroupe les installations Linux et Windows. Les commandes
APT/DNF sont centralisées dans `utils/packageRepositories.ts` et correspondent
aux fichiers publiés par Fusion. Le canal `dev` nécessite WireGuard et la CA
fournie avec l'accès. Les paramètres `platform=linux|windows`, `channel=prod|dev`
et `manager=apt|dnf` permettent de partager une configuration d'installation.

```shell
npm test
npm run build
npx playwright install chromium
npm run test:functional
```

Les tests unitaires couvrent notamment la session, le cache et les fonctions de
présentation. Les tests Playwright valident les parcours publics et privés sur
desktop et smartphone avec une API simulée.

Pour utiliser un serveur de test déjà lancé :

```shell
PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173 npm run test:functional
PLAYWRIGHT_BASE_URL=http://127.0.0.1:4173 npm run test:visual
```

Les tests d'installation vérifient les liens de dépôt, les chemins de confiance,
la copie des commandes, le changement de canal et les dimensions des blocs sur
petit écran. Ils ne lancent pas les commandes APT/DNF sur le poste.

## Conteneur

```shell
docker compose up --build
```

L'image de production est construite en plusieurs étapes et n'embarque que la
sortie Nitro et les dépendances nécessaires à l'exécution. Un contrôle de santé
HTTP est inclus dans l'image.

## Supervision et espace worker

- `/workers` présente la participation au réseau ; `/workers/overview` ouvre le suivi authentifié d’un nœud.
- Le sélecteur utilise les identifiants annoncés par le réseau. Le choix est conservé dans ce navigateur, par compte ; il ne lie pas la propriété d’un nœud au compte.
- Les ressources et compteurs proviennent des réponses réseau. Une télémétrie absente reste indisponible, et un nœud hors ligne n’affiche pas d’utilisation actuelle.
- Les courbes conservent au maximum cinq minutes de mesures reçues depuis l’ouverture de la vue. Elles interrompent le tracé lors d’une donnée absente ou d’une interruption prolongée.
- Le récapitulatif d’un projet montre les unités de travail et les temps fournis par le service. L’API ne fournit actuellement aucun montant payé : les unités ne sont pas converties en euros ou en SOL.
- L’icône compacte `public/brand/silicium-icon.svg` dérive du monogramme Si. Le visuel de marque complet est conservé séparément.

La direction et les huit maquettes révisées sont dans `../design/mockups/precision-v4-2026-10-20/`. Le texte courant utilise 17–18 px à taille de navigateur par défaut ; les petits libellés utilisent au moins 15 px. Les tailles restent relatives au réglage du lecteur.
