# ci/ — scripts de CI

Appelés par `.github/workflows/ci.yml` et utilisables en local.

| Script | Rôle |
| --- | --- |
| `core_check.sh` | Contrôle principal (`make check`) : tests Python, raytracer, Docker optionnel. Variables : `CORE_CHECK_MODE`, `CORE_CHECK_SCOPE`, `CORE_CHECK_WITH_DOCKER` |
| `docker_e2e.sh` + `docker-compose.e2e.yml` + `e2e-manifest.json` | E2E complet en Docker : orchestrateur, workers et scénario (`tools/dev/e2e/`) |
| `p2p_kademlia_smoke.sh` | Deux nœuds Rust locaux échangent un enregistrement Kademlia |

## `runner/` — protection des runners auto-hébergés

Les runners du VPS gardent leur dossier de travail et `~/.cargo` d'un job à
l'autre (et plusieurs runners partagent `~/.cargo`). Un disque plein, un
nettoyage (« Reclaim self-hosted runner ») ou un job interrompu peuvent laisser
un état cassé que Cargo réutilise. Ces scripts le réparent avant de compiler :

| Script | Rôle |
| --- | --- |
| `runner/repair_rust_toolchains.sh` | Désinstalle les toolchains rustup qui ne marchent plus (ex. lien `solana` vers un cache supprimé) |
| `runner/repair_cargo_sources.py` | Compare chaque source de `~/.cargo/registry/src` à son archive `.crate` (fichiers et tailles) et supprime celles qui sont incomplètes ; tient les verrous de Cargo |
| `runner/retry_on_corruption.sh` | Lance une commande de build ; si elle échoue sur une corruption (`dep info` manquant, crate introuvable, source C incomplète), nettoie `target/` ou les sources et réessaie une seule fois |

Une vraie erreur de compilation ou de test n'est jamais réessayée.
