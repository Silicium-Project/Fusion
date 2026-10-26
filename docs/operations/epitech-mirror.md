# Miroir Epitech depuis un commit Fusion exact

`mirror-epitech.yml` est indépendant du déploiement. Une qualification réussie
de `main` peut déclencher la copie ; une relance manuelle exige l'identifiant
d'un run CI réussi sur un push `main`, avec `ci/required` réellement exécuté.
Le dépôt restant privé, le workflow est actuellement désactivé.

## Contenu et preuve

La destination existante est
`EpitechPromo2027/G-EIP-600-lil-6-1-eip-luis.fernandes`, branche `main`.
Seul le préfixe `fusion/` est remplacé. Son arbre Git doit être identique à
l'arbre du SHA qualifié. `.silicium-mirror.json` enregistre ce SHA, l'arbre et
le run source. L'historique et les fichiers Epitech extérieurs sont conservés.

Une répétition du même commit ne crée pas de nouveau commit. Une ancienne
qualification ne peut pas ramener le miroir à un ancêtre ; une divergence
distante fait échouer le push, sans `--force`. Examiner alors les références
et relancer depuis une qualification actuelle. Aucun build n'a lieu sur le VPS.

## Activation

Dans l'environnement protégé `epitech-mirror`, réservé à `main`, configurer
`MIRROR_SSH_KEY` (clé de déploiement limitée à la destination) et la variable
`MIRROR_KNOWN_HOSTS` après vérification de l'empreinte SSH. Ne pas réutiliser
un PAT d'écriture général. La clé n'apparaît jamais dans une URL Git.

Activer `SILICIUM_MIRROR_ENABLED=1` seulement après la revue de l'exposition et
de la destination. Une exécution bloquée n'empêche ni CI, ni publication, ni
déploiement. Le test `tests/dev/mirror.test.mjs` utilise deux dépôts temporaires
locaux et vérifie le contenu, la répétition et le refus d'un retour arrière.
