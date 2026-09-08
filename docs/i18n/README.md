# i18n developer guide

Translations cover the active Python CLI/TUI, workload messages, and
Network/Solana infrastructure scripts. The former C++ fragment runtime and Qt
viewer are no longer translation targets.

## Workflow

1. Define a `module.surface.message_name` key.
2. Add it to `i18n/locales/en-US.json`.
3. Add the translated value to each supported locale.
4. Use the Python or shell lookup helpers at the user-facing boundary.
5. Run the checks below.

```bash
python tools/check_utf8.py
python tools/check_i18n_locales.py --strict
python tools/check_i18n_hardcoded_strings.py --strict
python -m pytest tests/test_i18n_contract.py tests/test_i18n_locales.py
```

Covered paths are `silicium`, `tools/tui`, `networked`, `workloads`, and
`infra`. Machine-readable output, secrets, and protocol payloads must stay
stable and must not be translated.
