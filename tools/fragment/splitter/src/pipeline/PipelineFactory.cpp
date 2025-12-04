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
#include "splitter/support/HashService.hpp"
#include "splitter/support/Env.hpp"
#include "splitter/artifacts/DefaultSymbolIndexer.hpp"
#include "splitter/artifacts/DefaultLibraryResolver.hpp"
#include "splitter/artifacts/ReadelfLibraryResolver.hpp"
#include "splitter/artifacts/ObjdumpSymbolIndexer.hpp"
#include "splitter/artifacts/StdHashAlgorithm.hpp"

namespace splitter {

namespace {

HashService ChooseHashService(const PipelineConfig& config) {
    std::string choice = config.hash_algo;
    if (choice.empty()) {
        if (auto env = GetEnv("SPLITTER_HASH_ALGO"))
            choice = *env;
    }
    if (choice == "std")
        return HashService(std::make_shared<StdHashAlgorithm>());
    return MakeHashServiceFromEnv();
}

std::unique_ptr<ILibraryResolver> ChooseResolver(const PipelineConfig& config) {
    std::string choice = config.resolver;
    if (choice.empty()) {
        if (auto env = GetEnv("SPLITTER_LIB_RESOLVER"))
            choice = *env;
    }
    if (choice == "readelf")
        return std::make_unique<ReadelfLibraryResolver>();
    return std::make_unique<DefaultLibraryResolver>();
}

std::unique_ptr<ISymbolIndexer> ChooseIndexer(const PipelineConfig& config) {
    std::string choice = config.symbol_indexer;
    if (choice.empty()) {
        if (auto env = GetEnv("SPLITTER_SYMBOL_INDEXER"))
            choice = *env;
    }
    if (choice == "objdump")
        return std::make_unique<ObjdumpSymbolIndexer>();
    return std::make_unique<DefaultSymbolIndexer>();
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
        std::make_unique<Partitioner>(config.binary_path, analyzer, *extractor, hash_service);
    auto partitioning = std::make_unique<PartitioningPhase>(std::move(partitioner), *extractor);

    auto scanner = std::make_shared<LibraryScanner>(ChooseResolver(config), ChooseIndexer(config));
    auto hash_calc = std::make_shared<SummaryHashCalculator>(nullptr, hash_service);
    auto artifacts = std::make_unique<ArtifactsPhase>(
        std::make_unique<ArtifactBuilder>(config.output_dir.Value()),
        std::make_unique<SummaryWriter>(config.output_dir.Value(), scanner, hash_calc),
        config.parallel_artifacts);

    return std::make_unique<PipelineRunner>(std::move(config), std::move(disassembly),
                                            std::move(analysis), std::move(partitioning),
                                            std::move(artifacts));
}

}  // namespace splitter
