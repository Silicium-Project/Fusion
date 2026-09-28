# ci/ — scripts de CI

Appelés par `.github/workflows/ci.yml` et utilisables en local.

| Script | Rôle |
| --- | --- |
| `core_check.sh` | Contrôle principal (`make check`) : tests Python, raytracer, Docker optionnel. Variables : `CORE_CHECK_MODE`, `CORE_CHECK_SCOPE`, `CORE_CHECK_WITH_DOCKER` |
| `docker_e2e.sh` + `docker-compose.e2e.yml` + `e2e-manifest.json` | E2E complet en Docker : orchestrateur, workers et scénario (`tools/dev/e2e/`) |
| `p2p_kademlia_smoke.sh` | Deux nœuds Rust locaux échangent un enregistrement Kademlia |
