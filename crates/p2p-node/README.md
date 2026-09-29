# p2p-node (`p2p_node`)

Binaire du nœud Rust. **Prototype** : il n'est lancé en production par aucun
chemin. On peut l'essayer via `./silicium node start --experimental-p2p-node`.

## Ce qu'il fait

- identité libp2p Ed25519 persistée dans `<data-dir>/identity.key` ;
- transports TCP + QUIC, chiffrement Noise, multiplexage Yamux ;
- découverte : mDNS, Kademlia (stockage en mémoire), Identify, AutoNAT ; relais
  en mode serveur ;
- diffusion des tâches et des événements du journal de tâches sur le topic
  Gossipsub `silicium-network` ;
- pour chaque tâche reçue : exécution via `node-core::runtime` si la tâche le
  demande, sinon appel au `compute-daemon` (`/compute` puis `/verify`), puis
  signalement au `reputation-bridge`.

## Configuration

| Variable / option | Défaut | Rôle |
| --- | --- | --- |
| `API_PORT` / `--api-port` | `9092` | Port de l'API HTTP locale |
| `SILICIUM_API_BIND` | `127.0.0.1` | Adresse d'écoute de l'API ; hors loopback, le jeton est obligatoire |
| `SILICIUM_NODE_CONTROL_TOKEN` | — | Jeton `Authorization: Bearer` exigé par `/publish` et `/tasks` (pas `/health`) |
| `SILICIUM_TRUSTED_PUBLISHERS` / `--trusted-publisher` | — | Peer ids dont les tâches sont exécutées ; sans liste, les tâches des autres pairs sont ignorées |
| `SILICIUM_ACCEPT_UNTRUSTED_TASKS` | `0` | `1` : exécuter les tâches de n'importe quel pair (réseau de test uniquement) |
| `SILICIUM_ALLOW_REMOTE_WASM` | `0` | `1` : autoriser une tâche à lancer un module WASM du dossier de travail (jamais d'image Docker) |
| `SILICIUM_COMPUTE_TIMEOUT_S` | `300` | Borne d'un appel au compute-daemon (+ 30 s) |
| `SILICIUM_COMPUTE_TOKEN` | — | Jeton envoyé au compute-daemon s'il en exige un |
| `SILICIUM_DATA_DIR` / `--data-dir` | `/data` | Identité et journal de tâches |
| `SILICIUM_BOOTSTRAP_PEERS` / `--bootstrap-peers` | — | Multiaddr des pairs d'amorçage, séparées par des virgules |
| `SILICIUM_ENABLE_QUIC_LISTENER` / `--enable-quic`, `--disable-quic` | activé | Écoute QUIC |
| `SILICIUM_DISPATCH_SEED` / `--dispatcher-seed` | `7` | Graine du sélecteur de nœuds |
| `SILICIUM_HW_BUCKET` | détecté | Force la catégorie matérielle |
| `COMPUTE_DAEMON_URL` | `http://127.0.0.1:9090` | Adresse du compute-daemon |
| `REPUTATION_BRIDGE_URL` | `http://127.0.0.1:9091` | Adresse du reputation-bridge |

## API HTTP

| Méthode | Route | Rôle |
| --- | --- | --- |
| `POST` | `/publish` | Publie une tâche sur le réseau |
| `GET` | `/tasks/{task_id}` | État dérivé du journal de tâches |
| `GET` | `/health` | Santé |

## Organisation du code

| Module | Contenu |
| --- | --- |
| `src/main.rs` | Démarrage et boucle d'événements (API → réseau, gossipsub → traitement) |
| `src/config.rs` | Options CLI, variables d'environnement, catégorie matérielle |
| `src/storage.rs` | Clé d'identité et journal de tâches signé sur disque |
| `src/swarm.rs` | Comportement libp2p, construction du swarm, publication DHT/gossipsub |
| `src/admission.rs` | Tâches acceptées : éditeurs de confiance, assainissement, jeton de l'API |
| `src/api.rs` | API HTTP locale |
| `src/processing.rs` | Traitement d'une tâche (runtime, compute, vérification, réputation) |
| `src/task.rs` | Charges utiles réseau (`NetworkTask`, `GossipMessage`) |

## Construire, tester, conteneur

```bash
cargo test -p p2p_node --locked
docker build -f crates/p2p-node/Dockerfile .   # depuis Network/ : contexte = racine du workspace
```

## Sécurité

- Une tâche reçue par gossipsub n'est exécutée que si sa source (signée) est
  un éditeur de confiance (ou le nœud lui-même).
- Toute tâche est assainie (`TaskEnvelope::sanitize_remote`) : ni image Docker,
  ni dossier de travail, ni variables d'environnement venant de l'éditeur ;
  `scene_path` doit être un chemin relatif sans `..` (résolu dans le dossier de
  travail du compute-daemon) ; le chemin de sortie est choisi localement
  (`<task_id>/output.ppm`).
- L'API refuse d'écouter hors loopback sans `SILICIUM_NODE_CONTROL_TOKEN`.
- Les appels au compute-daemon et au reputation-bridge ont un timeout.

## Limites connues

- Chaque nœud de confiance qui reçoit une tâche la calcule ; le résultat du
  sélecteur est ignoré.
- Pas de découpage en fragments, pas de transfert de fichiers entre pairs : la
  scène doit déjà être dans le dossier de travail.
- Vérification locale seulement (contre l'engagement de jalons renvoyé par le
  compute-daemon), pas encore par un autre pair.
- Ports P2P aléatoires (`tcp/0`, `udp/0`) : injoignable derrière un pare-feu.
