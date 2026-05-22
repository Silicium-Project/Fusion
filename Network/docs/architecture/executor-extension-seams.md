# Executor Extension Seams (Interface Map)

This document records executor polymorphic seams and their interface contracts.

## Scope

- backend selection seam
- API boundary seam for backend execution
- hashing strategy seam used by summary/JSON reconciliation
- runner strategy review

## Backend selection seam

- **Contracts**:
  - `executor/include/backend/ExecutionBackend.hpp` → `IExecutionBackend`
  - `executor/include/backend/ExecutionBackend.hpp` → `IExecutionBackendFactory`
- **Implementations**:
  - `EmulatedExecutionBackend`
  - `NativeExecutionBackend`
  - factory variants in `ExecutionBackendEmu.cpp` / `ExecutionBackendNative.cpp`
- **Wiring**:
  - `make_backend_factory()` returns `std::unique_ptr<IExecutionBackendFactory>`
  - CLI/API selection path consumes the interface end-to-end.

## API boundary seam

- **Contract**: `IExecutionBackend::run(const ExecutionEntry&, FragmentExecutor&, ExecutionResult&)`
- **Consumers**:
  - `executor/src/cli/Cli.cpp`
  - `executor/src/api/FragmentApi.cpp`
- **Intent**: caller code remains agnostic to emulated/native backend internals.

## Hash strategy seam

- **Contract**: `executor/include/support/Hash.hpp` → `IHasher`
- **Implementations**:
  - `Fnv1aHasher`
  - `StdHasher`
  - `DomainHasher` decorator
- **Consumers**:
  - `JsonHasher`
  - partition summary hash verification (`PartitionSummary.cpp`)

## Runner strategy review

- `EmulatedRunner` and `NativeRunner` remain concrete by design.
- Reason: they are performance-sensitive internals tied to backend implementation details.
- Extension remains at backend seam (`IExecutionBackend`) rather than introducing an extra runtime virtual layer in hot paths.

## Compatibility policy

- Legacy type aliases are temporarily kept:
  - `ExecutionBackendFactory` → `IExecutionBackendFactory`
  - `Hasher` → `IHasher`
- New code should use `I*` names as primary contract types.
