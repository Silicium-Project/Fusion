# Silicium Backend

API HTTP du site Silicium. Elle gère les comptes, les sessions JWT, les tâches distribuées, la télémétrie réseau et le rattachement vérifié d’un portefeuille Solana.

## Responsabilités

- comptes et sessions : `POST /register`, `POST /login`, `POST /refresh`, `/user` ;
- preuve de portefeuille : `POST /user/wallet/challenge`, puis `POST /user/wallet` avec une signature Ed25519 ;
- tâches : création multipart, pagination, annulation, résultat et détail d’exécution sous `/jobs` ;
- recherche dans des documents : dépôt des documents (`internal/documents`), collections, recherche `GET /jobs/{id}/search`, ouverture d’un document `GET /jobs/{id}/documents`, export de l’index par `GET /jobs/{id}/result` ;
- réseau : pairs et travaux RPC agrégés sous `/jobs/network` ;
- supervision publique : `/health`, `/healthz` et `/status` ;
- contrat OpenAPI : `/docs/openapi.yaml` dans l’image déployée.

L’API ne remplace pas l’orchestrateur ni la couche Solana. Elle expose leurs états canoniques au site et rattache chaque trace au bon utilisateur.

## Développement

Les variables requises sont décrites dans [`doc/env-variables.md`](doc/env-variables.md). Pour une exécution locale :

```sh
docker compose up --build
```

Vérifications avant publication :

```sh
go test ./...
go vet ./...
```

Le serveur applique des délais HTTP bornés, un arrêt gracieux, des identifiants de requête, des en-têtes de sécurité et une récupération des paniques. Le snapshot `/status` est mis en cache cinq secondes ; les données privées restent `no-store`.

## Déploiement

Le repository Fusion référence ce dépôt comme sous-module. Sa CI synchronise les gitlinks validés, construit les images et déploie la stack sur le VPS. Une réussite locale ne remplace pas un workflow Fusion et son job de déploiement au vert.
