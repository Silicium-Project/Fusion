# i18n developer guide

Translations cover the Network/Solana infrastructure shell scripts
(`infra/bin/`). The former Python CLI/TUI, the C++ fragment runtime and the Qt
viewer are gone and are no longer translation targets.

## Workflow

1. Define a `module.surface.message_name` key.
2. Add it to `i18n/locales/en-US.json`.
3. Add the translated value to each supported locale.
4. Add it to `i18n/shell/<locale>.sh` and use `sil_i18n_echo` (`infra/bin/i18n.sh`).
5. Run the checks below.

```bash
python tools/dev/quality/check_utf8.py
python tools/dev/quality/check_i18n_locales.py --strict
python -m pytest tests/test_i18n_contract.py tests/test_i18n_locales.py
```

Covered path: `infra`. Machine-readable output, secrets, and protocol payloads must stay
stable and must not be translated.
