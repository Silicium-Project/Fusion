# Splitter Extension Seams (Interface Map)

This document inventories splitter extension seams and the interface contracts that govern them.

## Scope

- analyzer selection and composition
- artifact writing pipeline seam
- library resolver/symbol indexer strategy seam
- hash algorithm strategy seam

Non-extension concrete pipeline steps are intentionally excluded.

## Analyzer seam

- **Contract**: `analysis/IInstructionAnalyzer.hpp` (`IInstructionAnalyzer`)
- **Implementations**: `X86_64InstructionAnalyzer`, `ArmInstructionAnalyzer`, `RiscVInstructionAnalyzer`, `GuiInstructionAnalyzer`, `CompositeInstructionAnalyzer`
- **Factory**: `analysis/InstructionAnalyzerFactory.hpp`
- **Consumption point**: `pipeline/AnalysisPhase.hpp` + `partitioning/Partitioner.hpp` use `std::shared_ptr<const IInstructionAnalyzer>`

## Artifact writer seam

- **Contracts**:
  - `artifacts/IArtifactBuilder.hpp` (`IArtifactBuilder`)
  - `artifacts/ISummaryWriter.hpp` (`ISummaryWriter`)
- **Implementations**:
  - `artifacts/ArtifactBuilder.hpp` (`ArtifactBuilder`)
  - `artifacts/SummaryWriter.hpp` (`SummaryWriter`)
- **Consumption point**: `pipeline/ArtifactsPhase.hpp` now consumes `std::unique_ptr<IArtifactBuilder>` and `std::unique_ptr<ISummaryWriter>`
- **Factory/registry wiring**: `pipeline/PipelineFactory.cpp` constructs concrete writers and passes them as interface pointers into the `PhaseRegistry` artifacts phase.

## Library resolution/indexing seam

- **Contracts**:
  - `artifacts/ILibraryResolver.hpp` (`ILibraryResolver`)
  - `artifacts/ISymbolIndexer.hpp` (`ISymbolIndexer`)
  - `artifacts/ILibraryScanner.hpp` (`ILibraryScanner`)
- **Implementations**:
  - resolvers: `DefaultLibraryResolver`, `ReadelfLibraryResolver`
  - indexers: `DefaultSymbolIndexer`, `ObjdumpSymbolIndexer`
  - composite scanner: `LibraryScanner`, `PeLibraryScanner`
- **Factory**: `artifacts/LibraryScannerFactory.hpp`
- **Consumption point**: `artifacts/SummaryWriter.hpp` consumes `std::shared_ptr<const ILibraryScanner>`

## Hash strategy seam

- **Contract**: `artifacts/HashAlgorithm.hpp` (`IHashAlgorithm`)
- **Implementations**: `FnvHashAlgorithm`, `StdHashAlgorithm`
- **Factory**: `artifacts/HashAlgorithmFactory.hpp`
- **Consumption point**:
  - `support/HashService.hpp` uses `std::shared_ptr<IHashAlgorithm>`
  - `artifacts/SummaryHashCalculator.hpp` creates per-operation hasher instances via the interface contract

## Registry/factory boundary rule

- At extension seams, pipeline wiring should consume interface contracts (`I*`) and keep concrete selection in factories/registry setup code.
- Concrete non-seam phase logic (`DisassemblyPhase`, `AnalysisPhase`, `PartitioningPhase`) stays unchanged unless it introduces a new extension seam.
