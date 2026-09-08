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

### networked

Mandatory interfaces/seams:

- **Transport seam**: direct HTTP, UDP hole-punching, and relay fallback must
  remain behind the active network transport contract.
- **Content seam**: local files, mesh content, and scheduler-provided blobs
  must use the shared content-reference contract.
- **Role runtime seam**: compute, verify, and storage roles must enter through
  the role/runtime contract instead of duplicating queue handling.

Concrete-first allowed:

- peer discovery, durable queue bookkeeping, and deterministic protocol
  helpers with one active implementation.

### workloads

Mandatory interfaces/seams:

- **Manifest seam**: every workload is selected through the versioned manifest
  schema and catalog rather than an ad-hoc CLI branch.
- **Result seam**: workload outputs, receipts, and verification attestations
  must use stable JSON contracts.

Concrete-first allowed:

- deterministic raytracer stages and bounded workload-specific transforms until
  a second implementation is actually required.

### mcp and control plane

Mandatory interfaces/seams:

- **Connector seam**: HTTP, MCP, and protobuf/ZeroMQ control paths must expose
  the same task and event semantics.
- **Policy seam**: authentication and allow/deny rules must be evaluated at
  the control boundary, not scattered through workload code.

Concrete-first allowed:

- the local durable export store while it remains the single source of truth.

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
