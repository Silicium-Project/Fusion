# tools/dev/ — outillage développeur (Python)

Rien ici n'est installé chez un utilisateur ni lancé sur le serveur de
production. Ces outils peuvent rester en Python.

| Dossier | Contenu | Commande type |
| --- | --- | --- |
| [`e2e/`](e2e/) | Scénario E2E Docker (`e2e_scenario.py`), workers et orchestrateur de test, sonde VPS, test de charge | `ci/docker_e2e.sh`, `python3 tools/dev/e2e/load_test.py --help` |
| [`world/`](world/) | Démo « world mesh » en Docker (`world_node.py`), wallet Solana de test, interface web locale | `python3 tools/dev/world/world_node.py up` |
| [`quality/`](quality/) | Contrôles UTF-8, i18n (locales, chaînes codées en dur), budgets de performance | `python3 tools/dev/quality/check_utf8.py` |
| [`release/`](release/) | Preflight Solana devnet (le manifeste de mise à jour est publié par `Fusion/deploy/linux/publish-update-manifest.sh`) | `python3 tools/dev/release/solana_devnet_preflight.py --json` |
| [`tui/`](tui/) | Interface terminal opérateur (textual / curses / headless) | `./silicium tui` |

Les scripts se lancent depuis la racine de `Network/` ; ceux qui importent
`tools.*` ajoutent eux-mêmes la racine au `sys.path`.

Documentation associée : `docs/development/load-testing.md`,
`docs/development/performance-budgets.md`, `docs/development/tui.md`,
`docs/operations/world-mesh-docker.md`, `docs/operations/solana-devnet.md`,
`docs/i18n/README.md`.
