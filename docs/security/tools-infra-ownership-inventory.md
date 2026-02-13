# Tools/Infra C++ Ownership Inventory

Issue target: #103

Date: 2026-02-13

## Scope

Checked trees:
- `tools/**`
- `infra/**`

Checked file types:
- `*.cpp`, `*.hpp`, `*.h`, `*.cc`, `*.cxx`

Rule used:
- `cpp.no_unsafe_allocation`

Repro command:

```bash
python tools/style_check.py \
  --rules cpp.no_unsafe_allocation \
  --include "tools/**/*.cpp" --include "tools/**/*.hpp" --include "tools/**/*.h" \
  --include "infra/**/*.cpp" --include "infra/**/*.hpp" --include "infra/**/*.h" \
  --format json
```

## Findings

### `infra/**`

- No C++ files matched in `infra/**`.
- Result: explicit N/A for ownership-style C++ checks in this tree.

### `tools/**`

Detected ownership-style violations in:
- `tools/tui/stdio_core.cpp:178`
- `tools/tui/stdio_core.cpp:181`

Observed pattern:
- Raw pointer handle declaration (`FILE* pipe`) used with `popen/_popen` and `pclose/_pclose`.

Risk/impact:
- Ownership and cleanup depend on manual discipline around C handle lifecycle.
- Pattern is localized and currently cleaned up, but remains policy-noncompliant with the gate rule.

Recommended remediation:
- Wrap `FILE*` in RAII (`std::unique_ptr<FILE, custom_deleter>`), or
- Refactor to a safer process wrapper abstraction with deterministic close semantics.

## Follow-up

A dedicated remediation issue was created for the findings:
- #170
