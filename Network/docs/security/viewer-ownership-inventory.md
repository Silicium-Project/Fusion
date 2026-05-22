# Viewer Ownership-Sensitive Inventory

Issue target: #102

Date: 2026-02-13

## Scope

Checked trees:
- `viewer/include/**`
- `viewer/src/**`
- `viewer/tests/**`

Checked file types:
- `*.cpp`, `*.hpp`, `*.h`, `*.cc`, `*.cxx`

Primary rule:
- `cpp.no_unsafe_allocation`

Repro commands:

```bash
# baseline
python tools/style_check.py --rules cpp.no_unsafe_allocation --format json

# focused viewer hotspots
python tools/style_check.py --rules cpp.no_unsafe_allocation --path viewer/src/GraphWindow.cpp --format json
python tools/style_check.py --rules cpp.no_unsafe_allocation --path viewer/src/GraphWindow.hpp --format json
```

Inventory summary (viewer-only findings): 11

## Findings (prioritized)

| Priority | File:Line(s) | Ownership semantics | Risk class | Proposed remediation pattern |
|---|---|---|---|---|
| P1 | `viewer/src/GraphWindow.cpp:35,36,43,45,46` | Manual `new` for Qt scene/view and raw pointer member usage (`scene_`, `view_`, returned item pointers) | Medium: ownership intent depends on Qt parent-child conventions and implicit lifetime coupling | Keep Qt parenting but encode ownership explicitly: use `QPointer`/references for non-owning members, avoid raw `new` at call site with helper factory wrappers |
| P1 | `viewer/src/GraphWindow.hpp:24,25` | Persistent raw pointer members for UI graph objects | Medium: nullability and lifetime ambiguity in class contract | Replace with `QPointer<QGraphicsScene>` / `QPointer<QGraphicsView>` (or references when guaranteed) |
| P2 | `viewer/src/GraphWindow.cpp:385,398,416,429` | Temporary raw pointers to QGraphics items returned by scene factory methods | Low runtime risk (scene owns items), but policy/style debt | Use immediate-use references where possible, or `auto* const` wrapped by comments/contracts; centralize item creation in helper to keep ownership explicit |

## Summary

- P0: 0
- P1: 2 hotspots
- P2: 1 hotspot

Highest-priority remediation starts with the class-level ownership contract in:
- `viewer/src/GraphWindow.hpp`
- `viewer/src/GraphWindow.cpp`

## Follow-up

- Existing parent remediation track: #75
- Focused viewer patch issue: #174
