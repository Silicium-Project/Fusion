# AGENT SUMMARY (Network)

**Resume**
Ce depot fournit une stack complete pour le projet Silicium :
- Un environnement Docker pour lancer un noeud Solana (localnet/devnet/testnet/mainnet).
- Un proxy TLS (Caddy) et une option de stack securisee WireGuard.
- Une chaine C++ de partitionnement/execution de binaires (splitter -> executor -> worker).
- Un viewer Qt pour visualiser les fragments.
- Un catalogue de workloads et une CLI Python pour orchestrer l'ensemble.

**Chiffres cles**
- Fichiers: 323
- Lignes approx: 22620
- Langages dominants: C++ (majoritaire), Bash, Python, YAML/JSON, C, ASM
- Licence: MIT (`LICENSE`)

**Architecture globale**
- Flux compute local: binaire -> `splitter` -> `summary.json` + fragments -> `fragment_executor` -> `worker` -> resultats.
- Flux reseau Solana: `docker compose` -> image `solanalabs/solana:stable` + entrypoint Silicium -> noeud local/dev/test/main + proxy TLS -> option WireGuard.

**Composants principaux**
- CLI et orchestration: `silicium` (alias `silicium-cli`). Gere tests, clean, ledgers, workloads, services Docker.
- Splitter: partitionneur C++ qui desassemble et genere fragments + `summary.json`.
- Executor: executeur de fragments (emu ou natif), libs partagees, JIT en memoire.
- Worker: orchestrateur d'execution (queue ou topo-sort), modes emu/native/dynamo, gestion de patchs memoire.
- Viewer: appli Qt de visualisation de graphe de fragments.
- Catalogue workloads: manifests + README pour profils calcul et verification.

**Structure du depot**
- `infra/`: Docker Compose, entrypoint Solana, proxy TLS, stack WireGuard.
- `splitter/`: pipeline d'analyse et partitionnement C++.
- `executor/`: execution de fragments (emu/natif) + libs.
- `worker/`: orchestrateur d'execution + DynamoRIO.
- `viewer/`: viewer Qt.
- `catalog/`: workloads calcul/verification.
- `docker/`: images de build/runtime (worker, GUI runner, headless).
- `tests/`: tests Python (entrypoint + manifests).
- `tools/`: generation assets de coverage.
- `ci/`: scripts E2E + tests images Docker.

**Infra Docker et reseau**
- Compose multi-profils: `infra/docker-compose.yml` (localnet/devnet/testnet/mainnet + proxy).
- Entrypoint Solana: `infra/docker/solana-entrypoint.sh` (cles, config CLI, solana-validator/test-validator).
- Proxy TLS Caddy: `infra/docker/reverse-proxy/caddy-entrypoint.sh`.
- Stack securisee WireGuard: `infra/secure-stack/`.

**Build et dependances**
- C++17, `g++`, `make`, binutils (`objdump`, `readelf`).
- Python 3 + `pytest`, `pyyaml` (`requirements-dev.txt`).
- Qt 5/6 + CMake pour `viewer`.
- Docker fortement utilise (tests, builds, DynamoRIO).

**Tests et CI**
- Tests Python: `tests/test_entrypoint.py`, `tests/test_manifests.py`.
- Tests C++ via image `silicium/cpp-tests` (splitter/executor/worker).
- CI GitHub Actions: `.github/workflows/tests.yml`, `release.yml`, `mirror.yml`.
- Scripts locaux: `ci/e2e.sh`, `ci/test_images.sh`.

**Etat d'avancement**
| Domaine | Statut | Notes |
| --- | --- | --- |
| Infra Solana (Docker Compose) | Fait | Localnet/devnet/testnet/mainnet + volumes ledger. |
| Proxy TLS (Caddy) | Fait | Modes `local`, `acme`, `internal`, endpoint `/healthz`. |
| Stack securisee WireGuard | Fait | RPC isole, acces via VPN. |
| Splitter C++ | Fait | Partitionnement + generation `summary.json`. |
| Executor (emu) | Fait | Emulation stable, usage principal. |
| Executor (native) | En cours | Fonctionnel mais instable selon fragments. |
| Worker (queue/emu/native) | Fait | Orchestration locale + patchs memoire. |
| Worker (DynamoRIO) | Fait | Execution via conteneur `dynamorio-runner`. |
| Worker (connector HTTP) | En cours | Mode present mais non branche. |
| Viewer Qt | Fait | Visualisation graph des fragments. |
| Catalogue workloads | Fait | Profils calcul + verification. |
| Tests + CI | Fait | Pytest + C++ tests + coverage worker. |
| On-chain programs + API/UI | A faire | Decrit comme architecture cible, pas code ici. |

**Artefacts generes**
- `splitter/run_output/**`: fragments + `summary.json`.
- `fragment_executor.log`: sortie standard capturee.
- `docs/coverage/worker/**`: rapports et badges coverage.

**Points d'attention**
- Environnement Linux/Docker quasi indispensable (scripts Bash + binutils).
- Mode `--native` du fragment executor peut crasher selon le binaire.
- Analyse principalement ELF x86_64 meme si des modules multi-arch existent.
- Sur Windows, preferer WSL2 ou un host Linux.

**Roadmap courte (proposee)**
1. Stabiliser `executor --native` (tests cibles, meilleure gestion PLT/GOT, garde-fous).
2. Brancher le connecteur HTTP du worker (API minimale + contrat JSON stabilise).
3. Ajouter un `silicium doctor` (diagnostic env: Docker, binutils, Qt, WSL).
4. Ameliorer la portabilite Windows/WSL (doc + scripts compatibles).
5. Ajouter un diagramme d'architecture dans `docs/` (mermaid).

**References importantes**
- `README.md`
- `silicium`
- `infra/docker-compose.yml`
- `infra/docker/solana-entrypoint.sh`
- `splitter/README.md`
- `executor/README.md`
- `worker/README.md`
- `viewer/README.md`
- `catalog/workloads/README.md`
