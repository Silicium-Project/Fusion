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

- `/`, `/service`, `/about`, `/contact` : présentation publique.
- `/auth` : connexion et création de compte.
- `/dashboard` : synthèse du compte et des calculs.
- `/jobs`, `/jobs/new`, `/jobs/:id` : création et suivi d'un calcul.
- `/network`, `/nodes` : capacité agrégée et installation d'un nœud.
- `/profile` : identité, sécurité et portefeuille Solana.

Le client conserve le jeton d'accès pour les appels courts et utilise le jeton
de renouvellement lorsque la session expire. Les données non sensibles sont
mises en cache avec une durée de vie courte ; les opérations d'écriture
invalident les entrées concernées. Les vues privées sont servies avec
`Cache-Control: no-store`.

## Développement

```shell
npm ci
npm run dev
```

Le frontend écoute sur `http://localhost:3000`. Par défaut, l'API est appelée via
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
