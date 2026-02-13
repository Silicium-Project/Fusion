# Worker Ownership-Sensitive Inventory

Issue target: #101

Date: 2026-02-13

## Scope

Checked trees:
- `worker/include/**`
- `worker/src/**`
- `worker/tests/**`

Checked file types:
- `*.cpp`, `*.hpp`, `*.h`, `*.cc`, `*.cxx`

Primary rule:
- `cpp.no_unsafe_allocation`

Repro commands:

```bash
# baseline
python tools/style_check.py --rules cpp.no_unsafe_allocation --format json

# focused hotspots
python tools/style_check.py --rules cpp.no_unsafe_allocation --path worker/src/task/TaskSerializer.cpp --format json
python tools/style_check.py --rules cpp.no_unsafe_allocation --path worker/src/mcp/McpGuardedToolRegistry.cpp --format json
python tools/style_check.py --rules cpp.no_unsafe_allocation --path worker/src/backend/ExecutorClient.cpp --format json
```

Inventory summary (worker-only findings): 32

## Findings (prioritized)

| Priority | File:Line(s) | Ownership semantics | Risk class | Proposed remediation pattern |
|---|---|---|---|---|
| P1 | `worker/src/task/TaskSerializer.cpp:134,135,178,207,236,239,256,311,379` | Repeated raw pointer bridges around `json_t*`/C JSON APIs and object traversal | Medium: manual lifetime assumptions around C handles and nullable pointers | Introduce thin RAII wrapper for `json_t*` ownership and helper accessors returning safe optional/value types |
| P1 | `worker/src/mcp/McpGuardedToolRegistry.cpp:67,68,75` | Raw `json_t*` parse/use/free path for MCP args payload | Medium: error-path lifetime coupling and nullable raw pointer flow | Use RAII JSON owner (`unique_ptr` + `json_decref` deleter) and centralized parse helpers |
| P1 | `worker/src/backend/ExecutorClient.cpp:86` | Raw `void*` symbol pointer from `dlsym` before cast to function pointers | Medium: weakly-typed symbol ownership/validity handling | Encapsulate symbol load + cast in typed helper templates with explicit null/ABI checks |
| P2 | `worker/include/worker/io/Reporter.hpp:22` | Non-owning raw pointer member (`std::ostream* stream_`) | Low runtime risk but ownership intent is implicit | Replace with reference member (`std::ostream&`) or `std::reference_wrapper<std::ostream>` |
| P2 | `worker/tests/os_policy_routing_test.cpp:42,56,70,85,100,116,130,145,162,178,195,212` | Test-only raw pointer aliases (`auto* connector_ptr = connector.get()`) | Low production risk; policy debt in tests | Replace with references or explicit observer helper object in test fixture |
| P2 | `worker/tests/backend_connector_test.cpp:56,57,75,257` | Test env helper stores `const char*` and explicit `delete` patterns flagged by rule | Low production risk; brittle patterns in test scaffolding | Refactor env helper to value/reference semantics, remove manual delete in tests |
| P2 | `worker/tests/worker_state_reset_test.cpp:38,70` | Test raw pointer aliases from unique_ptr (`FakeConnector* fake_ptr`) | Low production risk; style debt | Replace with references to fixture-owned objects |

## Summary

- P0: 0
- P1: 3 hotspots
- P2: 4 hotspots

Highest-priority remediation starts with the JSON C-API bridges in:
- `worker/src/task/TaskSerializer.cpp`
- `worker/src/mcp/McpGuardedToolRegistry.cpp`

## Follow-up

- Existing parent remediation track: #74
- Focused worker patch issue: #173
