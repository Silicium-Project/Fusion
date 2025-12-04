#include "splitter/pipeline/PipelineFactory.hpp"

#include <memory>

#include "splitter/analysis/ObjdumpDisassembler.hpp"
#include "splitter/analysis/X86InstructionAnalyzer.hpp"
#include "splitter/artifacts/ArtifactBuilder.hpp"
#include "splitter/artifacts/LibraryScanner.hpp"
#include "splitter/artifacts/SummaryWriter.hpp"
#include "splitter/partitioning/BinaryExtractor.hpp"
#include "splitter/partitioning/Partitioner.hpp"
#include "splitter/pipeline/AnalysisPhase.hpp"
#include "splitter/pipeline/ArtifactsPhase.hpp"
#include "splitter/pipeline/DisassemblyPhase.hpp"
#include "splitter/pipeline/PartitioningPhase.hpp"

namespace splitter {

std::unique_ptr<PipelineRunner> PipelineFactory::BuildDefault(PipelineConfig config) {
    auto disassembly = std::make_unique<DisassemblyPhase>(
        std::make_unique<ObjdumpDisassembler>(config.binary_path.Value()));

    const auto& analyzer = X86InstructionAnalyzer::Instance();
    auto analysis = std::make_unique<AnalysisPhase>(analyzer);

    auto extractor = std::make_shared<BinaryExtractor>();
    std::unique_ptr<IPartitioner> partitioner =
        std::make_unique<Partitioner>(config.binary_path, analyzer, *extractor);
    auto partitioning = std::make_unique<PartitioningPhase>(std::move(partitioner), *extractor);

    auto scanner = std::make_shared<LibraryScanner>();
    auto artifacts = std::make_unique<ArtifactsPhase>(
        std::make_unique<ArtifactBuilder>(config.output_dir.Value()),
        std::make_unique<SummaryWriter>(config.output_dir.Value(), scanner),
        config.parallel_artifacts);

    return std::make_unique<PipelineRunner>(std::move(config), std::move(disassembly),
                                            std::move(analysis), std::move(partitioning),
                                            std::move(artifacts));
}

}  // namespace splitter
