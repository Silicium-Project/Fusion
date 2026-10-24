# infra/ — conteneurs et services locaux

Infrastructure de **développement et de test** du dépôt Network. Le déploiement
de production du site (BackEnd, FrontEnd, orchestrateur `p2p_node`, proxy) est
dans `Fusion/deploy/`, pas ici.

| Chemin | Rôle |
| --- | --- |
| `docker-compose.yml` + `Dockerfile` | Validateur Solana local (réseaux `silicium`, `testnet`, `devnet`, `mainnet`) et reverse proxy Caddy. *Attention : les services s'appellent `silicium-node*` mais ce sont des validateurs Solana, pas le nœud de calcul.* |
| `bootstrap/` | Nœud d'amorçage libp2p (`crates/p2p-node`) pour un VPS |
| `docker/` | Script d'entrée du validateur Solana, reverse proxy |
| `bin/` | `i18n.sh` (traductions shell), `run-with-proxy.sh` |
| `.env.example` | Modèle de variables d'environnement (ne jamais committer le vrai `.env`) |
| `miniworker.Dockerfile` + `miniworker-entrypoint.sh` | Image légère des workers de développement : nœud P2P, daemon de calcul et raytracer, sans privilèges |

Le Compose de déploiement des miniworkers est dans `Fusion/deploy/compose/`.
Il garde un volume d'identité par conteneur, limite chaque processus à une
petite part du VPS et filtre les workloads autorisés. Ces identités restent
des conteneurs d'un même hôte, pas des machines indépendantes.
Chaque volume reçoit aussi un wallet Solana Devnet distinct dans
`/data/solana-wallet.json` (mode 0600). L'image n'imprime que l'adresse
publique ; Compose ne finance pas et n'enregistre pas ce wallet on-chain.

## Incohérences connues

- `bootstrap/` publie les ports `4001/tcp` et `4001/udp`, mais `p2p-node` écoute
  sur des ports aléatoires (`tcp/0`, `udp/0`) : à aligner.
