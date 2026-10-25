# Services déployés

Le fichier Compose accepte uniquement les images immuables du manifeste.
Le déploiement passe par `./dev deploy request` puis GitHub Actions.
Aucun build n'est lancé sur le VPS. Les volumes et secrets existants sont conservés.

Voir la [livraison](../../docs/operations/delivery.md) et
[l'adoption du VPS](../../docs/operations/bootstrap.md). Le runtime P2P encore
hébergé par systemd nécessite une migration et un drainage qualifiés avant
l'activation des mises à jour progressives. Un endpoint de santé ne prouve pas
qu'un worker est inactif.
