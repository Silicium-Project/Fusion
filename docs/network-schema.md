# Schéma du runtime Network

## Architecture active

```mermaid
flowchart LR
    Browser[FrontEnd] --> Proxy[Proxy /api]
    Proxy --> Backend[BackEnd]
    Backend -->|Bearer control API| Node[silicium-node Rust]
    Node <-->|gossip + discovery| Peers[Pairs P2P]
    Node --> Compute[compute_daemon Rust]
    Node --> Reputation[reputation_bridge]
    Node --> Solana[Solana layer]
    Catalog[Catalogue de workloads] --> Node
```

Le BackEnd n'écrit pas de fichiers d'export pour piloter les nouveaux jobs :
il soumet et suit les tâches via l'API `/v1` de `silicium-node`. Les artefacts
restent dans le plan de données du workload ; l'API est un plan de contrôle.

## Parcours d'une tâche

```mermaid
sequenceDiagram
    participant F as FrontEnd
    participant B as BackEnd
    participant N as silicium-node
    participant C as compute_daemon
    participant P as Pairs P2P

    F->>B: création/suivi du job
    B->>N: POST /v1/tasks (Bearer)
    N->>P: publication de l'enveloppe
    N->>C: calcul ou vérification
    C-->>N: résultat et hash
    N-->>B: GET /v1/tasks
    B-->>F: état du job
```

Consulter [node-control-api.md](node-control-api.md) pour le contrat HTTP et
[p2p-direct-transport-contract.md](p2p-direct-transport-contract.md) pour le
transport entre pairs.
