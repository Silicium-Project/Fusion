# Executor Ownership-Sensitive Inventory

Issue target: #100

Date: 2026-02-13

## Scope

Checked trees:
- `executor/include/**`
- `executor/src/**`
- `executor/tests/**`

Checked file types:
- `*.cpp`, `*.hpp`, `*.h`, `*.cc`, `*.cxx`

Primary rule:
- `cpp.no_unsafe_allocation`

Repro commands:

```bash
# full baseline (all modules)
python tools/style_check.py --rules cpp.no_unsafe_allocation --format json

# focused executor hotspots
python tools/style_check.py --rules cpp.no_unsafe_allocation --path executor/src/api/FragmentApi.cpp --format json
python tools/style_check.py --rules cpp.no_unsafe_allocation --path executor/include/api/FragmentApi.h --format json
python tools/style_check.py --rules cpp.no_unsafe_allocation --path executor/src/core/FragmentExecutor.cpp --format json
```

Inventory summary (executor-only findings): 78

## Findings (prioritized)

| Priority | File:Line(s) | Ownership semantics | Risk class | Proposed remediation pattern |
|---|---|---|---|---|
| P0 | `executor/src/api/FragmentApi.cpp:70,82,88,94,100,109,117,120,133,140,144,156,163,232,235,236,238,241,244,245,249,250,252,255` | Mixed manual ownership for exported C API objects and buffers (`malloc/calloc/free`, `new/delete`, raw pointer transit) | High: leak/double-free/exception-safety drift at ABI boundary | Replace manual ownership with RAII internals (`std::vector<uint8_t>`, `std::string`, `std::unique_ptr`), keep C ABI via narrow adapter wrappers for allocation/free handoff |
| P1 | `executor/include/api/FragmentApi.h:12,18,24,27,31,32,33,34,36,38,40,47,54,56,62,64,69,72,74,76,77,78` | Public C API surface uses raw pointers for buffers/handles | Medium: broad unsafe surface area, ambiguous ownership contract for callers | Keep ABI but document owner/free contract per field, introduce opaque handle + helper wrappers, and shrink exposed mutable pointer fields |
| P1 | `executor/src/core/FragmentExecutor.cpp:280,282,283,292,293,351,517` | Internal raw pointer aliases in execution path | Medium: alias lifetime/ownership ambiguity in core runtime | Replace raw pointers with references, iterators, or `std::span`; where nullable, use `std::optional<std::reference_wrapper<T>>` |
| P1 | `executor/src/partition/PartitionSummary.cpp:25,28,70,304,379,392,397,406,457` | Raw pointer use in summary parsing/materialization path | Medium: lifetime drift in parsing pipeline and serialization bridges | Use value types and smart-pointer adapters around external C parser handles; avoid naked pointer fields in internal data flow |
| P1 | `executor/src/runtime/Runner.cpp:100,104,340` | Runtime orchestration raw pointer aliases | Medium: nullability and lifetime coupling in orchestration path | Replace with references/optional-reference and explicit ownership-bearing objects |
| P1 | `executor/src/support/JsonHasher.cpp:33,34,49` | Raw pointer interaction with JSON hashing utility | Medium: wrapper boundaries around external C APIs | Encapsulate external pointer handles in local RAII wrapper types with deterministic cleanup |
| P1 | `executor/src/runtime/NativeRunner.cpp:192` | Raw pointer alias in native execution path | Medium: implicit lifetime coupling in native path | Convert to reference/iterator or optional-reference wrapper |
| P2 | `executor/tests/support_test.cpp:175,176,232,233,268,269` | Raw pointer patterns in test-only support code | Low production risk; still policy debt and false confidence risk | Refactor tests to same ownership-safe idioms (`std::array`, `std::vector`, smart pointers) to keep parity with production policy |

## Summary

- P0: 1 hotspot (ABI allocation/free ownership)
- P1: 6 hotspots (runtime/core/parser utility ownership semantics)
- P2: 1 hotspot (test support ownership debt)

Highest priority remediation starts at `executor/src/api/FragmentApi.cpp` (manual allocation + release paths).

## Follow-up

- Existing parent remediation track: #73
- Focused executor patch issue: #172
