# p2p-node (`p2p_node`)

Binaire du nœud Rust. Le canal dev l'utilise désormais comme runtime de
référence pour le desktop et l'orchestrateur VPS ; le Python historique reste
uniquement un outil de migration et de comparaison.

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
    la tâche toutes les 10 s tant que personne ne la prend ou ne propose de
    la vérifier (workers arrivés après la publication, nouvelle tentative
    après un bail expiré, un retrait ou un rejet), finalise le résultat ;
  - **vérificateur** (`src/verifier.rs`, toutes les secondes, nœuds au rôle
    `verify` seulement) : pour un
    résultat d'un autre nœud en attente de vérification, propose de le
    vérifier ; une fois accepté par l'éditeur, contrôle que les jalons
    couvrent toute l'image, recalcule via le compute-daemon les blocs tirés
    au sort à partir de l'acceptation et publie son verdict (aucun verdict si
    le rendu local échoue : le créneau se libère pour un autre vérificateur) ;
  - **worker seul** (`src/peers.rs`) : quand un seul nœud compute/verify est
    sur le réseau, il peut vérifier son propre résultat (condition
    `allow_self_verification` signée par l'éditeur, active par défaut).
    L'orchestrateur (rôles `resource`/`storage`) ne compte pas comme worker ;
    un pair dont le heartbeat n'est pas encore arrivé compte comme worker. Le
    worker ne propose de se vérifier que s'il ne voit aucun autre worker, et
    l'éditeur n'accepte cette offre que si le demandeur est le seul worker
    qu'il voit (lui compris). Dès qu'un deuxième worker est présent, la
    vérification doit venir de lui. C'est moins fort qu'une vérification
    indépendante, et jamais rémunéré ;
  - **contenus** (`src/content.rs`, `src/fetch/`) : scènes et images de
    résultat sont rangées par hash sous `content/<sha256>` dans le dossier de
    travail et annoncées dans la DHT (enregistrements de fournisseur) ; un
    pair qui n'a pas un contenu cherche ses détenteurs (à défaut, tous les
    pairs connectés), le demande à l'un après l'autre par le protocole
    requête-réponse `/silicium/content/1` (64 Mio au plus) et ne garde que des
    octets dont le hash correspond ;
  - **jobs** (`src/jobs/`, `src/publishing.rs`) : une tâche publiée par
    l'API est découpée par son workload (voir « Workloads ») : tuiles d'image
    pour le raytracer (centre d'abord), morceaux d'octets pour sha256 ;
    chaque fragment est une tâche `<job>.f<NNN>`. Le manifeste du job est
    gardé sous `results/<job>.job.json` ; quand tous les résultats de
    fragments sont là, l'éditeur assemble le résultat du job
    (`results/<job>.ppm` et `.png`, ou `results/<job>.json`).
    Un nœud ne propose de prendre un fragment que s'il a un créneau de calcul
    libre (`SILICIUM_PARALLEL_TASKS`) : les autres tuiles restent ouvertes
    pour les autres nœuds ;
  - **ses propres tâches** : l'éditeur calcule aussi ses tuiles
    (`SILICIUM_WORK_OWN_TASKS`), mais n'accepte sa propre proposition que si
    personne d'autre ne s'est proposé, et seulement s'il ne voit aucun autre
    worker ou après 5 s d'attente ;
  - **résultats** (`src/results.rs`) : le worker publie son image sous
    `content://<sha256>` ; une fois la tâche finalisée, l'éditeur la
    télécharge, vérifie que chaque jalon approuvé par les vérificateurs
    correspond à l'image (à la place de la tuile), et la garde sous
    `results/<task_id>.ppm` ;
  - **rattrapage** (`src/backfill.rs`) : quand des événements attendent leurs
    prédécesseurs, le nœud les redemande sur le topic ; les pairs répondent ;
- calcul d'une tâche acceptée : exécution via `node-core::runtime` si la tâche
  le demande, sinon appel au `compute-daemon` (`/compute` puis `/verify` en
  auto-contrôle), puis signalement au `reputation-bridge`.

Les identifiants de tâche publiés par l'API sont préfixés par la clé du
journal du nœud (`<32 hex>.<nom>`, nom de 90 caractères au plus parmi
`[A-Za-z0-9._-]`, la place du suffixe de tuile `.f000` étant réservée) : seul ce nœud peut proposer, accepter,
finaliser ou annuler ces tâches.

## Configuration

| Variable / option | Défaut | Rôle |
| --- | --- | --- |
| `API_PORT` / `--api-port` | `9092` | Port de l'API HTTP locale |
| `SILICIUM_P2P_BIND` / `--p2p-bind` | `0.0.0.0` | Adresse d'écoute libp2p |
| `SILICIUM_P2P_PORT` / `--p2p-port` | `0` | Port TCP/QUIC libp2p (`0` = éphémère) |
| `SILICIUM_API_BIND` | `127.0.0.1` | Adresse d'écoute de l'API ; hors loopback, le jeton est obligatoire |
| `SILICIUM_NODE_CONTROL_TOKEN` | — | Jeton `Authorization: Bearer` exigé par `/publish` et `/tasks` (pas `/health`) |
| `SILICIUM_TRUSTED_PUBLISHERS` / `--trusted-publisher` | — | Peer ids dont les tâches sont exécutées, en plus des pairs d'amorçage dont l'adresse se termine par `/p2p/<peer id>` ; sans éditeur de confiance, les tâches des autres pairs sont ignorées |
| `SILICIUM_NODE_ROLES` | `compute,verify` | Rôles du nœud : `compute` prend des tâches, `verify` vérifie ; `resource`/`storage` (orchestrateur) ne sont pas des workers |
| `SILICIUM_COMPUTE_ROOT` | `$SILICIUM_DATA_DIR/work` | Dossier de travail partagé avec le compute-daemon (`content/`, `results/`) |
| `SILICIUM_MAX_FRAGMENTS` | `32` | Tuiles par job au plus (256 au maximum) |
| `SILICIUM_TARGET_PIXELS_PER_FRAGMENT` | `120000` | Taille visée d'une tuile, en pixels (raytracer) |
| `SILICIUM_TARGET_BYTES_PER_FRAGMENT` | `4194304` | Taille visée d'un morceau d'entrée, en octets (sha256) |
| `SILICIUM_PARALLEL_TASKS` | `1` | Tâches calculées en même temps par ce nœud |
| `SILICIUM_WORK_OWN_TASKS` | `1` | `0` : ne pas calculer les tâches publiées par ce nœud (éditeur sans compute-daemon) |
| `SILICIUM_ALLOW_SELF_VERIFICATION` | `1` | `0` : interdire l'auto-vérification quand ce nœud est le seul pair compute/verify (l'orchestrateur ne compte pas) |
| `SILICIUM_VERIFICATIONS_REQUIRED` | `1` | Vérifications par un autre pair exigées sur les tâches publiées par ce nœud (0 : résultat finalisé sans vérification) |
| `SILICIUM_ACCEPT_UNTRUSTED_TASKS` | `0` | `1` : exécuter les tâches de n'importe quel pair (réseau de test local uniquement : le nœud refuse de démarrer avec `SILICIUM_RELEASE_CHANNEL` `dev` ou `prod`) |
| `SILICIUM_ALLOW_REMOTE_WASM` | `0` | `1` : autoriser une tâche à lancer un module WASM du dossier de travail (jamais d'image Docker) |
| `SILICIUM_COMPUTE_TIMEOUT_S` | `300` | Borne d'un appel au compute-daemon (+ 30 s) |
| `SILICIUM_COMPUTE_TOKEN` | — | Jeton envoyé au compute-daemon s'il en exige un |
| `SILICIUM_DATA_DIR` / `--data-dir` | `/data` | Identité et journal de tâches |
| `SILICIUM_BOOTSTRAP_PEERS` / `--bootstrap-peers` | — | Multiaddr des pairs d'amorçage, séparées par des virgules ; avec `/p2p/<peer id>`, l'identité est vérifiée à la connexion et ce pair devient éditeur de confiance |
| `SILICIUM_EXPORT_DIR` | — | Export des pairs, heartbeat et métriques du BackEnd, et journal d'activité `node.events.ndjson` de l'app desktop |
| `SILICIUM_WORKLOAD_STORAGE_DIR` | — | Projections `raytracer-progress.json` et résumé |
| `SILICIUM_NODE_CONTROL_TOKEN` | — | Jeton de l'API `/v1` quand elle écoute hors loopback |
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
| `GET` | `/jobs/{job_id}` | Job publié par ce nœud : tuiles (région, état, image), image finale et PNG une fois réassemblés |
| `POST` / `GET` | `/v1/tasks` | Soumission et suivi des tâches du BackEnd |
| `POST` | `/v1/workloads/{root_job_id}/cancel` | Annulation d'un workload |
| `GET` | `/v1/peers` | Pairs et métriques pour le BackEnd |
| `GET` | `/health` ou `/healthz` | Santé |

## Workloads

Le journal de tâches, l'ordonnancement, le transfert des entrées et des
résultats, le protocole de vérification et les fichiers lus par le BackEnd
sont communs. Ce qui change d'un calcul à l'autre est derrière le trait
`Workload` (`src/workload/mod.rs`) :

| Étape | Qui | Méthode |
| --- | --- | --- |
| découper une tâche soumise en fragments | éditeur | `split` |
| calculer un fragment | worker | `execute` |
| vérifier le fragment d'un autre nœud | vérificateur | `verify` |
| contrôler un résultat téléchargé | éditeur | `accepts_result` |
| construire le résultat du job | éditeur | `assemble` |

| Identifiant | Entrée | Fragment | Vérification | Résultat |
| --- | --- | --- | --- | --- |
| `raytracer` (défaut) | scène `.cfg` | tuile d'image, rendue par le compute-daemon | blocs de lignes tirés au sort et re-rendus | `reassembled/render.ppm` + `.png` |
| `calcul/integrity/sha256` (alias `calcul/hash/sha256`) | n'importe quel fichier (64 Mio max : taille d'un contenu échangé entre pairs ; chaque worker télécharge l'entrée entière) | morceau d'octets, haché dans le nœud | recalcul complet du morceau | `result/sha256.json` : empreinte de chaque morceau, empreinte de la liste, `input_hash` si un seul morceau |

L'identifiant voyage avec chaque tâche (`TaskEnvelope::workload`, absent =
raytracer pour les éditeurs plus anciens) ; un nœud refuse une tâche d'un
workload qu'il ne connaît pas. **Ajouter un workload** : un module qui
implémente `Workload`, ajouté à `REGISTRY` dans `src/workload/mod.rs`, avec
ses tests ; le BackEnd doit aussi l'accepter (`ValidateWorkload`).

## Organisation du code

| Module | Contenu |
| --- | --- |
| `src/main.rs` | Démarrage et boucle d'événements (API → réseau, minuterie de l'éditeur, gossipsub, contenus) |
| `src/gossip.rs` | Messages reçus : événements du journal, demandes de rattrapage, tâches |
| `src/worker.rs` | Rôle worker : proposition, attente d'acceptation, bail, résultat ou retrait |
| `src/publisher/` | Rôle éditeur : acceptation (réputation, ancienneté), auto-vérification d'un worker seul, réannonce (`announce.rs`), finalisation ; tests dans `tests.rs` |
| `src/peers.rs` | Rôles du nœud, workers connectés, règle du worker seul |
| `src/activity.rs` | Travail en cours (envoyé dans le heartbeat) et journal `node.events.ndjson` lu par l'app desktop |
| `src/content.rs` | Magasin de contenus par hash (scènes, images), commandes vers la boucle |
| `src/fetch/` | Téléchargement entre pairs : fournisseurs DHT, requête-réponse, service ; test à deux nœuds dans `tests.rs` |
| `src/workload/` | Workloads (voir ci-dessous) : `raytracer/` (tuiles, rendu, jalons, réassemblage), `sha256.rs` (morceaux d'octets) |
| `src/jobs/` | Manifestes de jobs sur disque, assemblage du résultat par le workload du job ; tests dans `tests.rs` |
| `src/publishing.rs` | Publication d'une tâche de l'API : scène partagée, découpage, proposition, DHT, gossip |
| `src/results.rs` | Image finale d'une tâche finalisée : téléchargement, contrôle contre les jalons |
| `src/verifier.rs` | Rôle vérificateur : offre, recalcul des blocs tirés au sort, verdict |
| `src/backfill.rs` | Demande et envoi des événements manquants |
| `src/config.rs` | Options CLI, variables d'environnement, catégorie matérielle |
| `src/storage.rs` | Clé d'identité et journal de tâches signé sur disque |
| `src/swarm.rs` | Comportement libp2p, construction du swarm, publication DHT/gossipsub |
| `src/admission.rs` | Tâches acceptées : éditeurs de confiance, assainissement, jeton de l'API |
| `src/api.rs` | API HTTP locale |
| `src/processing.rs` | Contexte du nœud et appels HTTP communs aux daemons locaux (compute-daemon, réputation) |
| `src/task.rs` | Charges utiles réseau (`NetworkTask`, `GossipMessage`) |

## Construire, tester, conteneur

Test de bout en bout du réseau dev en local (un orchestrateur qui ne calcule
pas, des workers qui arrivent 5 s après la publication du job, confiance par
adresse d'amorçage épinglée) :

```bash
cargo build --release -p p2p_node -p compute_daemon -p silicium-raytracer
WORKERS=1 crates/p2p-node/scripts/e2e-local.sh workloads/raytracer/examples/silicium-multi-fragment-scene.cfg
WORKERS=2 crates/p2p-node/scripts/e2e-local.sh workloads/raytracer/examples/silicium-multi-fragment-scene.cfg
```

Avec un worker, il vérifie ses propres tuiles ; avec deux, chacun vérifie
celles de l'autre.

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
- L'image d'une tuile est contrôlée contre ses jalons après la
  finalisation : une image non conforme bloque le réassemblage du job au
  lieu de relancer la tuile.
- Le BackEnd garde ses chemins et ses fichiers historiques : le nœud projette
  maintenant directement la progression, le résumé, les PNG de fragments et
  les heartbeats dans `SILICIUM_WORKLOAD_STORAGE_DIR` et `SILICIUM_EXPORT_DIR`.
- Un contenu passe en une seule réponse : 64 Mio au plus (pas de reprise
  d'un transfert interrompu).
- Ports P2P aléatoires (`tcp/0`, `udp/0`) : injoignable derrière un pare-feu.
