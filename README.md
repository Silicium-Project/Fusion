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

Les couleurs de statut sont sémantiques : menthe pour un état actif, ambre pour
une attente, rouge pour un échec. Le violet est réservé aux micro-accents. Les
actions principales utilisent le graphite de la marque.

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

```shell
npm test
npm run build
npx playwright install chromium
npm run test:functional
```

Les tests unitaires couvrent notamment la session, le cache et les fonctions de
présentation. Les tests Playwright valident les parcours publics et privés sur
desktop et smartphone avec une API simulée.

## Conteneur

```shell
docker compose up --build
```

L'image de production est construite en plusieurs étapes et n'embarque que la
sortie Nitro et les dépendances nécessaires à l'exécution. Un contrôle de santé
HTTP est inclus dans l'image.
