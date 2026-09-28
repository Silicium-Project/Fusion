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
| `API_PORT` / `--api-port` | `9092` | Port de l'API HTTP locale (liée à `127.0.0.1`) |
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
| `src/api.rs` | API HTTP locale |
| `src/processing.rs` | Traitement d'une tâche (runtime, compute, vérification, réputation) |
| `src/task.rs` | Charges utiles réseau (`NetworkTask`, `GossipMessage`) |

## Construire, tester, conteneur

```bash
cargo test -p p2p_node --locked
docker build -f crates/p2p-node/Dockerfile .   # depuis Network/ : contexte = racine du workspace
```

## Limites connues

- Chaque nœud qui reçoit une tâche la calcule ; le résultat du sélecteur est ignoré.
- Pas de découpage en fragments, pas de transfert de fichiers entre pairs,
  auto-vérification seulement.
- API sans authentification ; tâches du réseau acceptées sans contrôle d'émetteur.
- Ports P2P aléatoires (`tcp/0`, `udp/0`) : injoignable derrière un pare-feu.
- Appels HTTP internes sans timeout.
