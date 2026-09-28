# Vue d'ensemble — comment Silicium s'assemble

```mermaid
flowchart LR
    U[Utilisateur] --> F[FrontEnd<br/>Nuxt]
    F -->|/api| B[BackEnd<br/>Go]
    B --> DB[(PostgreSQL)]
    B -->|jobs| N[Réseau<br/>Network]
    D[App desktop<br/>apps/silicium-node] -->|installe et lance| N
    N --> S[(Programme Solana<br/>Network/solana-layer)]
```

| Composant | Où | Déployé par |
| --- | --- | --- |
| FrontEnd | `FrontEnd/` | `deploy/compose/docker-compose.yml` (service `frontend`) |
| BackEnd | `BackEnd/` | `deploy/compose/docker-compose.yml` (service `backend`) |
| Orchestrateur réseau (VPS) | `Network/` | `deploy/systemd/silicium-orchestrator.service` |
| API expérimentale MCP | `Network/tools/mcp_server.py` | `deploy/systemd/silicium-experiment-api.service` |
| Pont de réputation | `Network/crates/reputation-bridge` | `deploy/compose/docker-compose.yml` |
| Nœuds de calcul | `Network/` via l'app desktop | installeurs publiés par `deploy/` (Windows, AppImage, .deb, .rpm) |
| Reverse proxy, TURN, VPN dev | `deploy/nginx`, Compose, `deploy/vpn` | `deploy/` |

Le fonctionnement détaillé du réseau (ce qui tourne aujourd'hui, la cible Rust,
le parcours d'un job) est décrit dans
[`Network/docs/architecture/overview.md`](../../Network/docs/architecture/overview.md).
Le contrat de fichiers entre le BackEnd et le réseau est dans
[`Network/docs/contracts/backend-files.md`](../../Network/docs/contracts/backend-files.md).
