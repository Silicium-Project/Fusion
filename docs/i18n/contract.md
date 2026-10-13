# i18n Core Contract

This contract defines how user-facing strings are keyed, stored, and resolved.

Developer workflow:

- `docs/i18n/README.md`

## Scope

- Infra/scripts user-facing output (`infra/bin/`, `i18n/shell/`).
- The Rust node writes machine-readable logs and events only; the texts users
  read come from the desktop app and the website, which have their own
  catalogs.

## Key naming rules

- Format: `module.surface.message_name`
- Charset: lowercase ASCII, digits, and underscores.
- Separator: `.` between namespace segments.
- Example keys:
  - `infra.proxy.docker_missing`
  - `core.error`

## Namespace policy

- `core.*`: shared/common messages.
- `infra.*`: scripts/compose/proxy user output.

## Locale file format

- Format: JSON.
- Location: `i18n/locales/<locale>.json`
- Locale naming: BCP 47 style (`en-US`, `fr-FR`).

Required top-level structure:

```json
{
  "meta": {
    "locale": "en-US",
    "fallback": "en",
    "version": 1
  },
  "messages": {
    "core.example.key": "Example text"
  }
}
```

## Fallback chain

Resolve in this order:

1. Requested locale (example: `fr-FR`).
2. Language base (`fr`) if available.
3. Default locale (`en-US`).
4. Missing-key fallback token: `[missing:<key>]`.

## Missing-key behavior

- Emit a warning log once per missing key per process.
- Continue execution with safe fallback text.
- Never raise a hard failure for missing translation at runtime.

## Validation

Run `python tools/dev/quality/check_i18n_locales.py --strict` and
`python tools/dev/quality/check_i18n_hardcoded_strings.py --strict` before merging changes.
