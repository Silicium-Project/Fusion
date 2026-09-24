# Silicium — Backend API

API REST du projet Silicium. Elle assure la gestion des comptes utilisateurs, l'authentification JWT, le rattachement de portefeuille Solana, l'orchestration des tâches distribuées et la télémétrie réseau pair-à-pair.

---

## Table des matières

- [Prérequis](#prérequis)
- [Lancement rapide (Docker)](#lancement-rapide-docker)
- [Lancement en développement local](#lancement-en-développement-local)
- [Variables d'environnement](#variables-denvironnement)
- [Routes API](#routes-api)
- [Tests](#tests)
- [Déploiement](#déploiement)

---

## Prérequis

| Outil | Version minimale |
|---|---|
| [Go](https://go.dev/dl/) | 1.22.4 |
| [Docker](https://docs.docker.com/get-docker/) | 24+ |
| [Docker Compose](https://docs.docker.com/compose/install/) | v2+ |

---

## Lancement rapide (Docker)

C'est la méthode recommandée. Elle démarre automatiquement la base de données PostgreSQL et l'API.

**1. Copier et configurer le fichier d'environnement**

```bash
cp .env.example .env
```

> Éditez `.env` avec vos propres valeurs (voir [Variables d'environnement](#variables-denvironnement)).

**2. Construire et démarrer les services**

```bash
docker compose up --build
```

Pour lancer en arrière-plan :

```bash
docker compose up --build -d
```

**3. Vérifier que l'API est en ligne**

```bash
curl http://localhost:8080/healthz
# → ok
```

**4. Arrêter les services**

```bash
docker compose down
```

Pour supprimer aussi le volume de la base de données :

```bash
docker compose down -v
```

---

## Lancement en développement local

Pour lancer l'API directement sur la machine (sans Docker), une base PostgreSQL doit être accessible.

**1. Installer les dépendances**

```bash
go mod download
```

**2. Configurer l'environnement**

Créez un fichier `.env` à la racine ou exportez les variables directement dans votre shell :

```bash
export DATABASE_URL="host=localhost user=silicium password=siliciumpwd123 dbname=silicium_database port=5432 sslmode=disable"
export JWT_SECRET_KEY="votre_secret_jwt"
export CORS_ALLOWED_ORIGINS="http://localhost:3000"
```

**3. Lancer l'API**

```bash
go run ./cmd
```

Le serveur écoute par défaut sur `0.0.0.0:8080`. Vous pouvez changer l'hôte et le port via les variables `HOST` et `PORT`.

---

## Variables d'environnement

| Variable | Défaut | Requis | Description |
|---|---|---|---|
| `DATABASE_URL` | — | ✅ | DSN PostgreSQL (ex. `host=db user=… password=… dbname=… port=5432 sslmode=disable`) |
| `POSTGRES_DB` | — | ✅ (Docker) | Nom de la base de données PostgreSQL |
| `POSTGRES_USER` | — | ✅ (Docker) | Utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | — | ✅ (Docker) | Mot de passe PostgreSQL |
| `JWT_SECRET_KEY` | — | ✅ | Clé secrète pour la signature des tokens JWT (chaîne longue et aléatoire) |
| `CORS_ALLOWED_ORIGINS` | `*` | ❌ | Origines CORS autorisées, séparées par des virgules (ex. `http://localhost:3000`) |
| `SILICIUM_SOLANA_RPC` | `https://api.devnet.solana.com` | ❌ | URL du nœud RPC Solana |
| `SILICIUM_SOLANA_PROGRAM_ID` | — | ❌ | Program ID du smart contract Solana |
| `HOST` | `0.0.0.0` | ❌ | Adresse d'écoute du serveur HTTP |
| `PORT` | `8080` | ❌ | Port d'écoute du serveur HTTP |

> **Note :** Ne jamais commiter un `.env` contenant de vraies secrets. Ajoutez-le à `.gitignore`.

---

## Routes API

### 🔓 Publiques

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/health` | Health check simple |
| `GET` | `/healthz` | Health check (utilisé par Docker) |
| `GET` | `/status` | Snapshot d'état du système (mis en cache 5 s) |
| `POST` | `/register` | Créer un compte utilisateur |
| `POST` | `/login` | S'authentifier, retourne un JWT |
| `POST` | `/refresh` | Rafraîchir le token JWT |
| `GET` | `/docs/openapi.yaml` | Contrat OpenAPI |

### 🔒 Authentifiées (JWT requis)

**Utilisateur**

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/user` | Récupérer le profil de l'utilisateur courant |
| `PUT/PATCH` | `/user` | Mettre à jour le profil |
| `DELETE` | `/user` | Supprimer le compte |
| `PUT` | `/user/password` | Changer le mot de passe |
| `POST` | `/user/wallet/challenge` | Émettre un challenge de signature Ed25519 |
| `POST` | `/user/wallet` | Rattacher un portefeuille Solana (signature vérifiée) |

**Tâches distribuées**

| Méthode | Route | Description |
|---|---|---|
| `POST` | `/jobs` | Créer une nouvelle tâche (multipart) |
| `GET` | `/jobs` | Lister les tâches (paginé) |
| `GET` | `/jobs/{id}` | Détail d'une tâche |
| `POST` | `/jobs/{id}/cancel` | Annuler une tâche |
| `GET` | `/jobs/{id}/result` | Résultat d'une tâche |
| `GET` | `/jobs/{id}/dashboard` | Tableau de bord d'exécution |
| `GET` | `/jobs/{id}/fragments/{index}/preview` | Prévisualiser un fragment |

**Réseau**

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/jobs/network/peers` | Liste des pairs du réseau P2P |
| `GET` | `/jobs/network/tasks` | Tâches agrégées sur le réseau |
| `POST` | `/jobs/network/tasks/{id}/cancel` | Annuler une tâche réseau |

---

## Tests

```bash
# Lancer tous les tests
go test ./...

# Avec la couverture de code
go test -cover ./...

# Vérifications statiques
go vet ./...
```

---

## Déploiement

Le dépôt **Fusion** référence ce repo comme sous-module. Sa CI synchronise les gitlinks validés, construit les images Docker et déploie la stack sur le VPS via Docker Compose.

> ⚠️ Une réussite locale ne remplace **pas** un workflow Fusion au vert. Toujours valider via la CI avant de considérer un déploiement comme réussi.

### Caractéristiques du serveur

- Délais HTTP bornés (`ReadTimeout`, `WriteTimeout`, `IdleTimeout`)
- Arrêt gracieux sur `SIGINT` / `SIGTERM` (15 s max)
- Identifiants de requête automatiques (`X-Request-ID`)
- En-têtes de sécurité HTTP appliqués sur toutes les réponses
- Récupération des paniques (middleware `Recover`)
- Cache de 5 s sur `/status` ; données privées en `no-store`
