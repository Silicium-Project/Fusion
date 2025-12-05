#include "splitter/pipeline/PipelineFactory.hpp"

#include <cstdlib>
#include <memory>

#include "splitter/analysis/ObjdumpDisassembler.hpp"
#include "splitter/analysis/CompositeInstructionAnalyzer.hpp"
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
#include "splitter/pipeline/PhaseRegistry.hpp"
#include "splitter/pipeline/TimingPhase.hpp"
#include "splitter/support/HashService.hpp"
#include "splitter/support/Env.hpp"
#include "splitter/artifacts/LibraryScannerFactory.hpp"
#include "splitter/artifacts/HashAlgorithmFactory.hpp"

namespace splitter {

namespace {

HashService ChooseHashService(const PipelineConfig& config) {
    std::string choice = config.hash_algo;
    if (choice.empty()) {
        if (auto env = GetEnv("SPLITTER_HASH_ALGO"))
            choice = *env;
    }
    auto algo = HashAlgorithmFactory::Create(choice);
    return HashService(algo);
}

std::shared_ptr<ILibraryScanner> BuildScanner(const PipelineConfig& config) {
    std::string resolver = config.resolver;
    if (resolver.empty())
        if (auto env = GetEnv("SPLITTER_LIB_RESOLVER"))
            resolver = *env;

    std::string indexer = config.symbol_indexer;
    if (indexer.empty())
        if (auto env = GetEnv("SPLITTER_SYMBOL_INDEXER"))
            indexer = *env;

    return LibraryScannerFactory::Create(resolver, indexer);
}

}  // namespace

std::unique_ptr<PipelineRunner> PipelineFactory::BuildDefault(PipelineConfig config) {
    auto disassembly = std::make_unique<DisassemblyPhase>(
        std::make_unique<ObjdumpDisassembler>(config.binary_path.Value()));

    const auto& analyzer = CompositeInstructionAnalyzer::Default();
    auto analysis = std::make_unique<AnalysisPhase>(analyzer);

    auto extractor = std::make_shared<BinaryExtractor>();
    auto hash_service = ChooseHashService(config);
    std::unique_ptr<IPartitioner> partitioner =
        std::make_unique<Partitioner>(config.binary_path, analyzer, extractor, hash_service);
    auto partitioning = std::make_unique<PartitioningPhase>(std::move(partitioner), extractor);

    auto scanner = BuildScanner(config);
    auto hash_calc = std::make_shared<SummaryHashCalculator>(nullptr, hash_service);
    auto artifacts_builder = std::make_unique<ArtifactBuilder>(config.output_dir.Value());
    auto summary_writer =
        std::make_unique<SummaryWriter>(config.output_dir.Value(), scanner, hash_calc);

    PhaseRegistry registry;
    registry.Register("disassembly", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<DisassemblyPhase>(
            std::make_unique<ObjdumpDisassembler>(config.binary_path.Value())));
    });
    registry.Register("analysis", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<AnalysisPhase>(analyzer));
    });
    registry.Register("partitioning", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<PartitioningPhase>(
            std::make_unique<Partitioner>(config.binary_path, analyzer, extractor, hash_service),
            extractor));
    });
    registry.Register("artifacts", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<ArtifactsPhase>(
            std::make_unique<ArtifactBuilder>(config.output_dir.Value()),
            std::make_unique<SummaryWriter>(config.output_dir.Value(), scanner, hash_calc),
            config.parallel_artifacts));
    });

    auto phases = registry.CreateSequence({"disassembly", "analysis", "partitioning", "artifacts"});

    return std::make_unique<PipelineRunner>(std::move(config), std::move(phases[0]),
                                            std::move(phases[1]), std::move(phases[2]),
                                            std::move(phases[3]), nullptr);
}

}  // namespace splitter
