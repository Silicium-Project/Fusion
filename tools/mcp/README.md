# tools/mcp/ — serveur MCP/HTTP (runtime Python legacy)

Implémentation de l'API expérimentale MCP : un serveur HTTP authentifié qui
accepte des tâches et des requêtes post-job dans les files durables du
répertoire d'export, sert les ressources exportées par les workers et expose un
point d'entrée MCP (JSON-RPC sur Streamable HTTP, `POST /mcp`).

Le point d'entrée reste [`../mcp_server.py`](../mcp_server.py) : il est lancé en
script (`python3 tools/mcp_server.py --port …`), en module
(`python -m tools.mcp_server`) ou via `silicium mcp serve`, et ré-exporte les
noms publics (`McpTaskStore`, `McpRequestStore`, `main`, …). Contrat de l'API :
[`docs/contracts/mcp-connector-spec.md`](../../docs/contracts/mcp-connector-spec.md).

Comme le reste de `tools/*.py`, ce code est **legacy** : correctifs oui,
nouvelles fonctionnalités non (voir
[`docs/architecture/rust-migration.md`](../../docs/architecture/rust-migration.md)).

## Modules

| Module | Rôle |
| --- | --- |
| `constants.py` | URI des ressources, noms des outils, vocabulaires (rôles, priorités, protocoles), constantes HTTP |
| `validation.py` | Normalisation des champs des enveloppes (identifiants, rôles, priorité, `p2p_ref`, `on_chain`) |
| `persistence.py` | JSON compact, écriture atomique, ajout NDJSON, horloge UTC |
| `access_policy.py` | Listes d'autorisation / d'interdiction des outils et des ressources |
| `export_store.py` | Lecture d'une ressource dans le répertoire d'export, repli sur les snapshots |
| `task_store.py` | `McpTaskStore` : `tasks/<id>.json`, `tasks.queue.ndjson`, `tasks.<rôle>.queue.ndjson`, annulation |
| `request_store.py` | `McpRequestStore` : `requests/<id>.json` et files de requêtes (urgentes, par rôle) |
| `snapshot_store.py` | Snapshots persistants des ressources, rétention, export / import de bundles |
| `control_plane.py` | `control.request.json` (interruption, choix du mode d'exécution) |
| `metrics.py` | Compteurs Prometheus servis sur `/metrics` |
| `observability.py` | Journal structuré (`text` ou `json`) et regroupement journal + métriques |
| `app.py` | `McpHttpApp` : état partagé du serveur et exécution des outils |
| `http_io.py` | Lecture du corps JSON, réponses JSON |
| `discovery.py` | Réponse de découverte OAuth (non supporté) et document OpenAPI |
| `tool_catalog.py` | Descripteurs des outils MCP et gabarits de ressources |
| `auth.py` | Vérification du jeton Bearer (mixin du handler) |
| `handler_observe.py` | Journal d'accès et métriques par requête (mixin) |
| `handler_get.py` | Routes `GET` (mixin) |
| `handler_post.py` | Routes `POST` hors `/mcp` (mixin) |
| `handler_mcp.py` | Transport JSON-RPC de `POST /mcp`, lots, réponse SSE (mixin) |
| `mcp_methods.py` | Méthodes MCP : `initialize`, `resources/*`, `tools/*`, `ping` (mixin) |
| `handler.py` | `McpHttpHandler`, assemblé à partir des mixins |
| `cli.py` | Options de ligne de commande et `main()` |

`__init__.py` n'importe rien : importer `tools.mcp.task_store` ne charge pas la
pile HTTP.

## Tests

`tests/test_mcp_server.py` et `tests/test_silicium_mcp_cli.py`.
