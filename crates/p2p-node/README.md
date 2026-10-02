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
- journal de tâches partagé (`node-core::taskbook`, v2) :
  - **worker** (`src/worker.rs`) : pour une tâche reçue, propose de la prendre
    pour la tentative ouverte, attend que l'éditeur l'accepte (30 s), renouvelle
    son bail pendant le calcul, puis publie le résultat ou se retire ;
  - **éditeur** (`src/publisher/`, toutes les secondes) : accepte la
    meilleure proposition pour la tentative ouverte et le meilleur
    vérificateur (réputation dérivée du journal, puis ancienneté), réannonce
    la tâche quand une nouvelle tentative s'ouvre (bail expiré, retrait,
    rejet), finalise le résultat ;
  - **vérificateur** (`src/verifier.rs`, toutes les secondes) : pour un
    résultat d'un autre nœud en attente de vérification, propose de le
    vérifier ; une fois accepté par l'éditeur, contrôle que les jalons
    couvrent toute l'image, recalcule via le compute-daemon les blocs tirés
    au sort à partir de l'acceptation et publie son verdict (aucun verdict si
    le rendu local échoue : le créneau se libère pour un autre vérificateur) ;
  - **nœud seul** : quand il n'a aucun pair connecté, un nœud peut vérifier
    son propre résultat (condition `allow_self_verification` signée par
    l'éditeur, active par défaut) ; c'est moins fort qu'une vérification
    indépendante, et jamais rémunéré ;
  - **contenus** (`src/content.rs`, `src/fetch/`) : scènes et images de
    résultat sont rangées par hash sous `content/<sha256>` dans le dossier de
    travail et annoncées dans la DHT (enregistrements de fournisseur) ; un
    pair qui n'a pas un contenu cherche ses détenteurs (à défaut, tous les
    pairs connectés), le demande à l'un après l'autre par le protocole
    requête-réponse `/silicium/content/1` (64 Mio au plus) et ne garde que des
    octets dont le hash correspond ;
  - **résultats** (`src/results.rs`) : le worker publie son image sous
    `content://<sha256>` ; une fois la tâche finalisée, l'éditeur la
    télécharge, vérifie que chaque jalon approuvé par les vérificateurs
    correspond à l'image, et la garde sous `results/<task_id>.ppm` ;
  - **rattrapage** (`src/backfill.rs`) : quand des événements attendent leurs
    prédécesseurs, le nœud les redemande sur le topic ; les pairs répondent ;
- calcul d'une tâche acceptée : exécution via `node-core::runtime` si la tâche
  le demande, sinon appel au `compute-daemon` (`/compute` puis `/verify` en
  auto-contrôle), puis signalement au `reputation-bridge`.

Les identifiants de tâche publiés par l'API sont préfixés par la clé du
journal du nœud (`<32 hex>.<nom>`, nom de 95 caractères au plus parmi
`[A-Za-z0-9._-]`) : seul ce nœud peut proposer, accepter,
finaliser ou annuler ces tâches.

## Configuration

| Variable / option | Défaut | Rôle |
| --- | --- | --- |
| `API_PORT` / `--api-port` | `9092` | Port de l'API HTTP locale |
| `SILICIUM_API_BIND` | `127.0.0.1` | Adresse d'écoute de l'API ; hors loopback, le jeton est obligatoire |
| `SILICIUM_NODE_CONTROL_TOKEN` | — | Jeton `Authorization: Bearer` exigé par `/publish` et `/tasks` (pas `/health`) |
| `SILICIUM_TRUSTED_PUBLISHERS` / `--trusted-publisher` | — | Peer ids dont les tâches sont exécutées ; sans liste, les tâches des autres pairs sont ignorées |
| `SILICIUM_COMPUTE_ROOT` | `$SILICIUM_DATA_DIR/work` | Dossier de travail partagé avec le compute-daemon (`content/`, `results/`) |
| `SILICIUM_ALLOW_SELF_VERIFICATION` | `1` | `0` : interdire l'auto-vérification d'un nœud seul sur les tâches publiées |
| `SILICIUM_VERIFICATIONS_REQUIRED` | `1` | Vérifications par un autre pair exigées sur les tâches publiées par ce nœud (0 : résultat finalisé sans vérification) |
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
| `src/main.rs` | Démarrage et boucle d'événements (API → réseau, minuterie de l'éditeur, gossipsub, contenus) |
| `src/gossip.rs` | Messages reçus : événements du journal, demandes de rattrapage, tâches |
| `src/worker.rs` | Rôle worker : proposition, attente d'acceptation, bail, résultat ou retrait |
| `src/publisher/` | Rôle éditeur : acceptation (réputation, ancienneté), auto-vérification d'un nœud seul, réannonce, finalisation ; tests dans `tests.rs` |
| `src/content.rs` | Magasin de contenus par hash (scènes, images), commandes vers la boucle |
| `src/fetch/` | Téléchargement entre pairs : fournisseurs DHT, requête-réponse, service ; test à deux nœuds dans `tests.rs` |
| `src/results.rs` | Image finale d'une tâche finalisée : téléchargement, contrôle contre les jalons |
| `src/verifier.rs` | Rôle vérificateur : offre, recalcul des blocs tirés au sort, verdict |
| `src/backfill.rs` | Demande et envoi des événements manquants |
| `src/config.rs` | Options CLI, variables d'environnement, catégorie matérielle |
| `src/storage.rs` | Clé d'identité et journal de tâches signé sur disque |
| `src/swarm.rs` | Comportement libp2p, construction du swarm, publication DHT/gossipsub |
| `src/admission.rs` | Tâches acceptées : éditeurs de confiance, assainissement, jeton de l'API |
| `src/api.rs` | API HTTP locale |
| `src/processing.rs` | Exécution d'une tâche acceptée (runtime, compute, auto-contrôle, réputation) |
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

- Le résultat du sélecteur (`Dispatcher`) est ignoré.
- Pas de découpage en fragments : une tâche est l'image entière.
- Un contenu passe en une seule réponse : 64 Mio au plus (pas de reprise
  d'un transfert interrompu).
- Ports P2P aléatoires (`tcp/0`, `udp/0`) : injoignable derrière un pare-feu.
