# Vue d'ensemble de l'architecture

Ce document décrit **ce qui tourne réellement aujourd'hui** (branche `main`) et
**l'architecture cible**. Le passage de l'un à l'autre est décrit dans
[`rust-migration.md`](rust-migration.md).

## Composants du projet Silicium

| Composant | Dépôt / dossier | Langage | Rôle |
| --- | --- | --- | --- |
| FrontEnd | `Fusion/FrontEnd` | Nuxt 3 / TypeScript | Création et suivi des calculs par l'utilisateur |
| BackEnd | `Fusion/BackEnd` | Go | Comptes, sessions JWT, jobs ; pilote le réseau |
| Nœud réseau | `Network/` | Python (actuel) → Rust (cible) | Découverte des pairs, distribution, calcul, vérification |
| App desktop | `Fusion/apps/silicium-node` | Tauri (Rust + Vue) | Installe et supervise le nœud chez l'utilisateur |
| Couche Solana | `Network/solana-layer` | Anchor (Rust) + SDK TypeScript | Jobs on-chain, réputation, staking, récompenses |
| Déploiement | `Fusion/deploy` | Docker Compose, systemd, Nginx | Serveur (VPS), CI/CD, canaux dev/prod |

## Architecture actuelle (production, `main`)

```mermaid
flowchart LR
    U[Navigateur] --> P[Nginx /api]
    P --> B[BackEnd Go]
    B -->|lance run_network_job.py| J[Orchestration du job<br/>Python]
    B -->|POST /gossip/publish<br/>contrôles de tâches| O
    J --> O[Orchestrateur<br/>tools/network_node.py<br/>VPS :46100]
    O <-->|HTTP gossip + clé mesh| W1[Nœud utilisateur<br/>network_node.py :46101]
    O <-->|HTTP gossip + clé mesh| W2[Nœud utilisateur<br/>network_node.py]
    W1 -->|compute.py| R[silicium-raytracer<br/>crates/raytracer]
    O -->|node solana_layer_bridge.cjs| S[(Programme Solana)]
    B -->|lit les fichiers d'export JSON| O
```

Points clés :

- **Tout le plan réseau est en Python** : `tools/network_node.py` sert à la fois
  d'orchestrateur sur le VPS et de nœud de calcul chez les utilisateurs
  (lancé par l'app Tauri via `silicium node start`).
- **Le calcul lui-même est déjà en Rust** : le rendu passe par le binaire
  `silicium-raytracer` (`crates/raytracer`).
- **Le BackEnd lit des fichiers écrits par le runtime Python** (progression,
  fragments, reçus, heartbeat des pairs). C'est un contrat implicite ; voir
  [`../contracts/backend-files.md`](../contracts/backend-files.md).
- Les appels Solana passent par Node.js (`tools/solana_layer_bridge.cjs`).

## Parcours d'un job (actuel)

```mermaid
sequenceDiagram
    participant F as FrontEnd
    participant B as BackEnd
    participant J as run_network_job.py
    participant O as Orchestrateur (VPS)
    participant C as Nœud compute
    participant V as Nœud verify

    F->>B: POST /jobs (scène .cfg)
    B->>J: lance le job (sous-processus Python)
    J->>J: découpe l'image en tuiles
    J->>O: publie les tâches de fragments
    C->>O: réclame une tâche (pull)
    C->>C: rend la tuile (silicium-raytracer), hash des jalons
    C->>O: renvoie le fragment + reçu
    O->>V: défi sur un jalon choisi au hasard
    V->>O: verdict
    J->>J: réassemble l'image, écrit progression + reçus
    B-->>F: GET /jobs/{id} (lit les fichiers produits)
```

## Architecture cible (Rust)

```mermaid
flowchart LR
    B[BackEnd Go] -->|API /v1 + jeton| N[silicium-node<br/>crates/p2p-node]
    N <-->|libp2p : Noise, QUIC, Kademlia,<br/>Gossipsub, relay, DCUtR| M[Autres nœuds silicium-node]
    N --> CD[Calcul : crates/compute-daemon<br/>+ crates/raytracer]
    N --> RB[crates/reputation-bridge]
    RB --> S[(Programme Solana)]
```

Principes de la cible :

- un seul binaire `silicium-node` par machine, sans Python ni Node.js ;
- un plan de contrôle HTTP versionné (`/v1`) réservé au BackEnd, authentifié ;
- un plan de données libp2p entre nœuds : les fichiers circulent par hash de
  contenu, jamais par chemin ;
- des tâches signées par l'orchestrateur, vérifiées par un pair différent de
  celui qui a calculé.

## Où trouver quoi

- Organisation des dossiers : [`repository-layout.md`](repository-layout.md)
- Plan de migration : [`rust-migration.md`](rust-migration.md)
- Contrats (API, fichiers, protocoles) : [`../contracts/`](../contracts/)
