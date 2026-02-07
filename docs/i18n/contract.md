# i18n Core Contract

This contract defines how user-facing strings are keyed, stored, and resolved.

## Scope

- CLI/TUI Python strings.
- Worker/executor/splitter runtime user-facing text.
- Viewer UI strings.
- Infra/scripts user-facing output.

## Key naming rules

- Format: `module.surface.message_name`
- Charset: lowercase ASCII, digits, and underscores.
- Separator: `.` between namespace segments.
- Example keys:
  - `cli.shell.prompt`
  - `tui.status.running`
  - `worker.error.summary_not_found`
  - `viewer.menu.open_file`

## Namespace policy

- `core.*`: shared/common messages.
- `cli.*`: command-line shell/command messages.
- `tui.*`: terminal UI labels/status/errors.
- `splitter.*`, `executor.*`, `worker.*`: runtime components.
- `viewer.*`: Qt viewer messages.
- `infra.*`: scripts/compose/proxy user output.
- `workload.*`: workload catalog and validation messages.

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

## Child issue linkage

The following issues must implement this contract:

- `#112` Worker/executor/splitter extraction.
- `#113` CLI/TUI extraction.
- `#114` Viewer translation pipeline.
- `#115` Infra/scripts extraction.
- `#116` CI i18n gate.
- `#117` Locale packs baseline.
- `#118` i18n developer guide.
