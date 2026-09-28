# infra/ — conteneurs et services locaux

Infrastructure de **développement et de test** du dépôt Network. Le déploiement
de production du site (BackEnd, FrontEnd, orchestrateur, proxy) est dans
`Fusion/deploy/`, pas ici.

| Chemin | Rôle |
| --- | --- |
| `docker-compose.yml` + `Dockerfile` | Validateur Solana local (réseaux `silicium`, `testnet`, `devnet`, `mainnet`) et reverse proxy Caddy. *Attention : les services s'appellent `silicium-node*` mais ce sont des validateurs Solana, pas le nœud de calcul.* |
| `docker-compose.world.yml` | Testbed « world mesh » : nœuds Python conteneurisés (voir `docs/operations/world-mesh-docker.md`) |
| `bootstrap/` | Nœud d'amorçage libp2p (`crates/p2p-node`) pour un VPS |
| `docker/` | Dockerfiles et scripts d'entrée : Solana, outils Solana, nœud world, test de charge, reverse proxy |
| `systemd/silicium-node.service` | Unité d'exemple pour un nœud Python sur un serveur |
| `bin/` | `i18n.sh` (traductions shell), `run-with-proxy.sh` |
| `.env.example` | Modèle de variables d'environnement (ne jamais committer le vrai `.env`) |

## Incohérences connues

- `bootstrap/` publie les ports `4001/tcp` et `4001/udp`, mais `p2p-node` écoute
  sur des ports aléatoires (`tcp/0`, `udp/0`) : à aligner.
- `systemd/silicium-node.service` utilise l'ID de programme Solana
  `HyXT83…`, alors que le programme (`declare_id!`) et le BackEnd utilisent
  `A9bxX9…`.
