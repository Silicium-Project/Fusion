# tools/dev/ — outillage développeur (Python)

Rien ici n'est installé chez un utilisateur ni lancé sur le serveur de
production : le nœud, le calcul et l'API sont en Rust (`crates/`). Ces outils
peuvent rester en Python.

| Dossier | Contenu | Commande type |
| --- | --- | --- |
| [`quality/`](quality/) | Contrôles UTF-8 et parité des catalogues de traduction (`i18n/locales/`) | `python3 tools/dev/quality/check_utf8.py`, `python3 tools/dev/quality/check_i18n_locales.py --strict` |
| [`release/`](release/) | Preflight Solana devnet (le manifeste est signé dans le workflow GitHub Release de Fusion) | `python3 tools/dev/release/solana_devnet_preflight.py --json` |

Les scripts se lancent depuis la racine de `network/` ; leurs tests sont dans
`tests/` (`python3 -m pytest -q`).

Documentation associée : `docs/operations/solana-devnet.md`, `docs/i18n/README.md`.
