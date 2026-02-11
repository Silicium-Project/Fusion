# PE Fixture Corpus

Versioned PE fixtures used by regression tests across `splitter`, `executor`, and `worker`.

## Files

- `valid-minimal-pe64.exe`: valid PE32+ minimal fixture.
- `malformed-mz-only.exe`: malformed MZ-only binary (no valid PE signature).
- `unsupported-import-table-pe64.exe`: valid PE header with non-empty import table.

## Regeneration

From repository root:

```bash
python tools/generate_pe_fixture_corpus.py
```

This rewrites fixtures and `manifest.json` deterministically.
