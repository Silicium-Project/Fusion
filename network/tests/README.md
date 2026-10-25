# tests/ — tests pytest de l'outillage développeur

Le runtime réseau est en Rust : ses tests sont dans chaque crate
(`cargo test --workspace`, ou `cargo test -p <paquet>`) et le test de bout en
bout est `ci/e2e.sh`. Ce dossier ne teste que les outils Python de `tools/dev/`
et les fichiers de configuration du dépôt.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

| Fichiers | Couvre |
| --- | --- |
| `test_utf8.py` | `tools/dev/quality/check_utf8.py` : tous les fichiers du dépôt sont en UTF-8 |
| `test_i18n_contract.py`, `test_i18n_locales.py` | Catalogues `i18n/locales/` (structure, parité des langues) via `tools/dev/quality/check_i18n_locales.py` |
| `test_solana_integration_contract.py` | `tools/dev/release/solana_devnet_preflight.py`, scripts devnet et ID de programme du SDK |
| `test_entrypoint.py` (+ `conftest.py`, `testdata.txt`) | Script d'entrée du conteneur Solana (`infra/docker/solana-entrypoint.sh`) |
| `smoke/` | Smoke test du reverse proxy (`infra/docker-compose.yml`, nécessite Docker) |
