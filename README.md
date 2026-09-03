# FrontEnd

## Build
Launch using docker compose

```shell
docker compose up --build 
```
Ports :  
Frontend -> 3000

## Current Mock-up for the website (10/30)
<img width="1440" height="1024" alt="Silicium - Landing Page" src="https://github.com/user-attachments/assets/f66531ff-c48a-4c11-895f-51093b0a6620" />
<img width="1440" height="1024" alt="Silicium - App Dashboard(1)" src="https://github.com/user-attachments/assets/ca8d55f1-7cef-4b67-8bab-c933ba00e325" />
<img width="1440" height="1024" alt="Silicium - App Dashboard" src="https://github.com/user-attachments/assets/817fa73e-08b2-4b49-a86a-11a5b4322707" />       

### Notice
Not yet convince about the user Dashboard, currently too "raw" and too big elements.

## Connexion et inscription — fix/auth_site

Correction de l'authentification et de la navigation commune, sans
changement des fonctionnalités du dashboard, du réseau, du déploiement ou du protocole de session.

- Le bouton « S'inscrire » ouvre `/auth?mode=register`.
- Les erreurs sont visibles et une inscription réussie affiche une confirmation.
- La connexion accepte l'e-mail ou le nom d'utilisateur (avec sa casse enregistrée).
- Après connexion, user et admin arrivent sur l'accueil en conservant leur session.
  L'en-tête affiche alors « Dashboard » entre « Silicium » et « A propos ». À droite,
  un lien vers le profil affiche l'initiale et le username, comme sur le dashboard.
  Le profil est chargé via GET /user avec le token existant ; l'e-mail sert de repli
  en l'absence de username. Ces liens restent présents après rechargement et
  disparaissent à l'expiration de la session.
- La déconnexion depuis le profil supprime le cookie de session et ramène à l'accueil déconnecté.
- L'accueil et le dashboard partagent le composant `Header` : le lien « Silicium »
  ramène à l'accueil sans déconnecter. L'ancien bouton « Accueil » et le profil en
  doublon du dashboard sont retirés ; le solde SOL reste affiché dans son contenu.
  La page de connexion/inscription
  propose également un lien « Retour à l’accueil », sans déconnecter l'utilisateur.
- Le cookie `auth_token` existant expire avec le JWT (15 minutes), pas après 7 jours.
  Un ancien token expiré ne déclenche plus la redirection depuis l'accueil.
- Le renouvellement automatique et les cookies HttpOnly ne font pas partie de ce
  correctif. Après expiration, une nouvelle connexion est nécessaire.

## Pages publiques

- `/` : présentation du projet, du parcours de calcul et accès au dashboard.
- `/about` : principe de Silicium, architecture et statut de développement.
- `/service` : ancien contenu de l'accueil, état de l'API, manifeste de mise à jour,
  téléchargement Windows et rafraîchissement automatique. L'accueil ne lance plus ces vérifications.
- `/contact` : informations de contact et aide au signalement d'un problème.

`Header.vue` porte les liens publics et les actions de connexion/inscription pour
toutes les pages qui l'utilisent. `PublicPage.vue` partage la mise en page des pages
de présentation. La session reste inchangée en naviguant entre ces pages.

Configurer `NUXT_PUBLIC_CONTACT_EMAIL` pour afficher le lien de contact par e-mail
(voir `.env.example`). Sans cette valeur, la page annonce que les coordonnées ne
sont pas encore disponibles ; aucun faux formulaire d'envoi n'est affiché.
Les styles communs de présentation se trouvent dans `assets/css/main.css`.

Pour tester avec une API PostgreSQL déjà démarrée localement :

```powershell
$env:NUXT_PUBLIC_API_BASE='http://localhost:8080'
npm run dev
```

Ouvrir `http://localhost:3000`. L'API doit autoriser cette origine dans
CORS_ALLOWED_ORIGINS. En production, conserver le proxy `/api`.
Le lanceur de stack n'est pas modifié dans cette branche.

Vérification : `npm test`, `npm run build`, puis `npm run test:functional`
(Chromium doit être installé via `npx playwright install chromium`).
Les tests navigateur simulent l'API et couvrent inscription, erreurs, rôle admin
et ancien cookie expiré. Tester aussi personnellement une inscription puis une
connexion avec l'API réelle ; un mauvais mot de passe doit produire une erreur.
