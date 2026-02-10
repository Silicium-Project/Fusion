# Architecture Policy: Interface-First at Extension Seams

This document is the normative policy for when interfaces are required in Silicium modules and when concrete classes are preferred.

## Goals

- Keep extension points explicit and testable.
- Avoid speculative abstractions on stable single-implementation paths.
- Keep module boundaries evolvable without forcing broad refactors.

## Default Rules

1. **Interface mandatory at extension seams**:
   - when multiple implementations already exist, or
   - when a second implementation is planned in an active issue/milestone, or
   - when integration depends on external systems (HTTP, OS backends, storage, UI frontends).
2. **Concrete class preferred** for stable single implementation code paths inside a module.
3. **No interface extraction for “future maybe”** without a concrete second implementation driver.
4. **Factory/registry at seam entry** (composition root), not scattered dynamic selection in business logic.
5. **Tests must target the seam contract** when a seam is mandatory.

## Naming Convention

- Interface types use `I*` prefix (examples: `IExecutionBackend`, `ITuiConnector`).
- Concrete implementations use explicit capability names (examples: `HttpConnector`, `NativeExecutionBackend`).
- Factory/provider names are capability-oriented (`*Factory`, `*Registry`, `build_*`).

## Exception Process

If a contributor wants to:
- add an interface where policy says “optional”, or
- skip an interface where policy says “mandatory”,

they must include an **Architecture Exception Note** in the issue/PR description with:

1. decision scope (module + symbols),
2. why default policy does not fit,
3. migration and test impact,
4. rollback plan.

Without this note, maintainers should request changes.

## Mandatory Seams by Module

### splitter

Mandatory interfaces/seams:

- **Instruction/disassembly provider seam**: alternate disassembly or analysis providers must stay behind a contract.
- **Reporting/output writer seam**: console/json/multi reporter variants must remain swappable via shared contract.
- **Hashing service seam**: algorithm/provider changes must remain behind a stable hashing contract.

Concrete-first allowed:

- internal data holders and deterministic pipeline phases with single behavior.

### executor

Mandatory interfaces/seams:

- **Execution backend seam**: emulation/native backends must implement a shared execution contract (`IExecutionBackend` family).
- **Backend factory seam**: backend selection is centralized through factory contract(s), not ad-hoc branching.
- **Runtime integration seam**: OS/runtime specific executors must be isolated behind the backend contract.

Concrete-first allowed:

- pure domain structs and single-path helpers with no cross-runtime variability.

### worker

Mandatory interfaces/seams:

- **Backend connector seam**: direct/http (and future transports) must remain plug-compatible behind connector interfaces.
- **Execution backend target seam**: native/docker/wsl/http routing decisions must consume explicit capability contracts.
- **Telemetry/report sink seam**: output/report targets that can vary by environment must remain behind stable APIs.

Concrete-first allowed:

- orchestration code that coordinates already-abstracted seams without introducing new variability.

### tui

Mandatory interfaces/seams:

- **TUI connector seam**: in-process/stdio/http connectors must implement `ITuiConnector`.
- **Frontend seam**: textual/curses/headless frontends must follow shared app-level contracts and registry-based selection.
- **Command runner seam**: headless/testing command execution must stay injectable for deterministic tests.

Concrete-first allowed:

- rendering/layout code local to a single frontend backend.

## Review Checklist

For any new abstraction PR:

- Is this a real extension seam?
- Is there at least one existing or tracked second implementation need?
- Is contract-level testing included?
- Is business logic decoupled from implementation selection?

If any answer is “no”, prefer concrete code.
