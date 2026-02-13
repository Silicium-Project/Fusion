# Splitter Ownership-Sensitive Inventory

Issue target: #99

Date: 2026-02-13

## Scope

Checked trees:
- `splitter/include/**`
- `splitter/src/**`
- `splitter/tests/**`

Checked file types:
- `*.cpp`, `*.hpp`, `*.h`, `*.cc`, `*.cxx`

Primary rule:
- `cpp.no_unsafe_allocation`

Repro commands:

```bash
# broad scan (current tree)
python tools/style_check.py \
  --rules cpp.no_unsafe_allocation \
  --include "splitter/**/*.cpp" --include "splitter/**/*.hpp" --include "splitter/**/*.h" \
  --format json

# focused scan (ownership-sensitive candidates)
python tools/style_check.py \
  --rules cpp.no_unsafe_allocation \
  --path splitter/src/support/ShellCommand.cpp \
  --path splitter/src/support/Env.cpp \
  --path splitter/src/partitioning/BinaryExtractor.cpp \
  --format json
```

## Findings (prioritized)

| Priority | File:Line | Ownership semantics | Risk class | Proposed remediation pattern |
|---|---|---|---|---|
| P1 | `splitter/src/support/ShellCommand.cpp:18` | Raw owning process handle (`std::FILE* pipe`) returned by `popen`/`_popen`, manually closed by `pclose` | Resource lifetime leak on exceptional paths; fragile manual ownership | Wrap process handle in RAII (`std::unique_ptr<FILE, Deleter>`), with platform-specific deleter (`pclose`/`_pclose`) |
| P2 | `splitter/src/support/Env.cpp:9` | Non-owning C-string pointer from `std::getenv` copied into `std::string` | Low runtime risk; pointer lifetime tied to process environment; flagged by raw-pointer policy | Keep immediate copy pattern, optionally encapsulate in helper with documented ownership contract, or add narrow policy exception for getenv bridge |
| P2 | `splitter/src/partitioning/BinaryExtractor.cpp:61` | Non-owning alias pointer (`const SectionInfo*`) to element in local vector | Low/medium maintainability risk; alias invalidation risk if container mutation is introduced later | Replace raw pointer alias with index (`std::optional<size_t>`) or `std::reference_wrapper<const SectionInfo>` |

## Summary

- P0: 0
- P1: 1
- P2: 2

The highest-priority remediation target is `ShellCommand.cpp` because it owns an external process stream and currently relies on manual close discipline.

## Follow-up

Created remediation issue:
- #171
