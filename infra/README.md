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

## Incohérences connues

- `bootstrap/` publie les ports `4001/tcp` et `4001/udp`, mais `p2p-node` écoute
  sur des ports aléatoires (`tcp/0`, `udp/0`) : à aligner.
