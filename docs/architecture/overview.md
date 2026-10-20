# Vue d'ensemble de l'architecture

Ce document décrit **ce qui tourne aujourd'hui**. Le runtime réseau est
entièrement en Rust ; l'ancien runtime Python (nœud, orchestration, API MCP,
CLI) a été supprimé. L'historique de la bascule est dans
[`rust-migration.md`](rust-migration.md).

## Composants du projet Silicium

| Composant | Dépôt / dossier | Langage | Rôle |
| --- | --- | --- | --- |
| FrontEnd | `Fusion/FrontEnd` | Nuxt 3 / TypeScript | Création et suivi des calculs par l'utilisateur |
| BackEnd | `Fusion/BackEnd` | Go | Comptes, sessions JWT, jobs ; pilote l'orchestrateur par son API `/v1` |
| Nœud réseau | `Network/crates/p2p-node` | Rust | Orchestrateur sur le VPS, worker chez l'utilisateur : libp2p, journal de tâches, découpage, vérification, assemblage |
| Calcul | `Network/crates/compute-daemon`, `crates/raytracer`, `crates/embedding` | Rust | Exécution locale des tâches (rendu, sha256, embeddings) |
| App desktop | `Fusion/apps/silicium-node` | Tauri (Rust + Vue) | Installe et supervise `p2p_node` + `compute_daemon` chez l'utilisateur |
| Couche Solana | `Network/solana-layer` | Anchor (Rust) + SDK TypeScript | Jobs on-chain, réputation, staking, récompenses |
| Déploiement | `Fusion/deploy` | Docker Compose, systemd, Nginx | Serveur (VPS), CI/CD, canaux dev/prod |

## Architecture

```mermaid
flowchart LR
    U[Navigateur] --> P[Nginx /api]
    P --> B[BackEnd Go]
    B -->|API /v1 + jeton de contrôle| O[Orchestrateur<br/>p2p_node sur le VPS]
    B -->|lit heartbeat, progression,<br/>résumé (fichiers)| O
    O <-->|libp2p : Noise, QUIC, Kademlia,<br/>Gossipsub, relais, DCUtR| W1[Worker<br/>p2p_node chez l'utilisateur]
    O <-->|libp2p| W2[Worker]
    W1 --> C[compute_daemon<br/>+ silicium-raytracer]
```

Points clés :

- **Un seul binaire de nœud** (`p2p_node`) : l'orchestrateur du VPS (rôles
  `resource,storage`) et les workers des utilisateurs (rôles `compute,verify`)
  exécutent le même code avec une configuration différente.
- **Le BackEnd parle à l'orchestrateur par HTTP** : `POST /v1/tasks`
  (soumission), `POST /v1/workloads/{id}/cancel`, `GET /v1/peers`,
  `POST /v1/embedding/search`, avec le jeton `SILICIUM_NODE_CONTROL_TOKEN`.
- **Le BackEnd lit aussi des fichiers écrits par le nœud** (heartbeat, pairs,
  progression, résumé) : voir [`../contracts/backend-files.md`](../contracts/backend-files.md).
- **Seules les tâches signées par un éditeur de confiance sont exécutées** :
  le pair d'amorçage épinglé (`/p2p/<peer id>`) ou `SILICIUM_TRUSTED_PUBLISHERS`.
- Les fichiers circulent entre pairs **par hash de contenu** (SHA-256), jamais
  par chemin.

## Parcours d'un job

```mermaid
sequenceDiagram
    participant F as FrontEnd
    participant B as BackEnd
    participant O as Orchestrateur (p2p_node, VPS)
    participant C as Worker (calcul)
    participant V as Worker (vérification)

    F->>B: POST /jobs (scène, fichier ou documents)
    B->>O: POST /v1/tasks
    O->>O: prépare l'entrée, découpe en fragments (trait Workload)
    O-->>C: publie les tâches signées (gossip)
    C->>O: propose de calculer ; l'orchestrateur accepte (bail)
    C->>C: calcule le fragment (compute_daemon)
    V->>V: recalcule un échantillon (autre worker, ou le worker seul)
    O->>O: assemble le résultat, écrit progression et résumé
    B-->>F: GET /jobs/{id} (lit les fichiers produits)
```

Les workloads disponibles (`raytracer`, `calcul/integrity/sha256`,
`ai/embedding/multilingual-e5-small`) implémentent le trait `Workload` de
`crates/p2p-node/src/workload/` ; en ajouter un nouveau se fait en Rust, dans ce
module.

## Où trouver quoi

- Organisation des dossiers : [`repository-layout.md`](repository-layout.md)
- Recherche dans des documents : [`embedding-workload.md`](embedding-workload.md)
- Catalogue IA (modèles Hugging Face) : [`hf-workload.md`](hf-workload.md)
- API du nœud : `crates/p2p-node/README.md`
- Contrats (fichiers, programme Solana) : [`../contracts/`](../contracts/)
