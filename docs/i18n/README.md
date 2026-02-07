# i18n Developer Guide

This guide explains how to add or update translations across Python, C++, Qt, and scripts.

Core contract:

- `docs/i18n/contract.md`

Reference locale:

- `i18n/locales/en-US.json`

## Workflow

1. Define the message key.
2. Add or update the key in `i18n/locales/en-US.json`.
3. Add or update translated values in target locale files (for example `fr-FR.json`).
4. Wire the key in component code (Python, C++, Qt, or scripts).
5. Run validation checks before pushing.

## Key naming

- Format: `module.surface.message_name`
- Example: `worker.error.summary_not_found`
- Use lowercase ASCII plus `_` in the final segment.

## Component usage patterns

### Python CLI/TUI

- Replace user-facing literals with lookup keys.
- Keep fallback text safe for missing keys.
- Suggested namespace: `cli.*`, `tui.*`, `workload.*`.

### C++ runtime (worker/executor/splitter)

- Keep internal debug strings unchanged unless user-facing.
- Externalized user-facing messages should map to `worker.*`, `executor.*`, `splitter.*`.
- Missing keys must not crash runtime paths.

### Qt viewer

- Use `viewer.*` keys for UI labels, actions, dialogs, and errors.
- Keep key names stable to avoid translation churn.

### Infra/scripts

- Use `infra.*` keys for command output intended for users.
- Keep machine-parsed output stable and untranslated where required.

## Fallback behavior

Resolution order:

1. Requested locale (example `fr-FR`)
2. Language base (example `fr`)
3. Default locale (`en-US`)
4. Safe token: `[missing:<key>]`

Runtime behavior:

- Log missing keys once per process.
- Never hard-fail due to missing translations.

## Validation commands

Run from repository root:

```bash
python tools/check_utf8.py
python -m pytest tests/test_i18n_contract.py
python tools/check_i18n_locales.py --strict
```

Optional pre-check:

```bash
python -m pytest tests/test_i18n_contract.py tests/test_i18n_locales.py tests/test_workload_cli.py
```

## Common failure modes

- Key typo between code and locale files.
- Locale filename does not match `meta.locale`.
- Missing `messages` object in locale JSON.
- Accidental key rename causing fallback-only behavior.
- Using user-facing hardcoded strings instead of keys.

## Review checklist

- New user-facing string has a key.
- `en-US` contains the key and value.
- Locale update keeps contract structure.
- Fallback behavior remains safe.
- Validation commands pass locally.

## Related issues

- `#112` runtime extraction for worker/executor/splitter
- `#113` extraction for CLI/TUI
- `#114` Qt translation pipeline
- `#115` infra/scripts extraction
- `#116` CI gate for hardcoded strings
- `#117` baseline locale packs
