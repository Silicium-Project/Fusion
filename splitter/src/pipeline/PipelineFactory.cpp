#include "pipeline/PipelineFactory.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <memory>

#include "analysis/CompositeInstructionAnalyzer.hpp"
#include "analysis/DisassemblerFactory.hpp"
#include "analysis/InstructionAnalyzerFactory.hpp"
#include "artifacts/ArtifactBuilder.hpp"
#include "artifacts/HashAlgorithmFactory.hpp"
#include "artifacts/LibraryScanner.hpp"
#include "artifacts/LibraryScannerFactory.hpp"
#include "artifacts/SummaryWriter.hpp"
#include "partitioning/BinaryExtractor.hpp"
#include "partitioning/Partitioner.hpp"
#include "pipeline/AnalysisPhase.hpp"
#include "pipeline/ArtifactsPhase.hpp"
#include "pipeline/DisassemblyPhase.hpp"
#include "pipeline/PartitioningPhase.hpp"
#include "pipeline/PhaseRegistry.hpp"
#include "pipeline/ReporterFactory.hpp"
#include "pipeline/TimingPhase.hpp"
#include "support/HashService.hpp"
#include "support/ShellCommand.hpp"
#include "support/SystemContext.hpp"

namespace splitter {

namespace {

std::string GetEnvValue(const SystemContext& system, const std::string& key) {
    if (!system.env)
        return {};
    if (auto env = system.env->Get(key))
        return *env;
    return {};
}

bool CommandExists(const std::string& cmd, const SystemContext& system);

HashService ChooseHashService(const PipelineConfig& config, const SystemContext& system) {
    std::string choice = config.hash_algo;
    if (choice.empty())
        choice = GetEnvValue(system, "SPLITTER_HASH_ALGO");
    auto algo = HashAlgorithmFactory::Create(choice);
    return HashService(algo);
}

std::shared_ptr<ILibraryScanner> BuildScanner(const PipelineConfig& config,
                                              const SystemContext& system) {
    std::string resolver = config.resolver;
    if (resolver.empty())
        resolver = GetEnvValue(system, "SPLITTER_LIB_RESOLVER");

    std::string indexer = config.symbol_indexer;
    if (indexer.empty())
        indexer = GetEnvValue(system, "SPLITTER_SYMBOL_INDEXER");

    if (resolver == "readelf" && !CommandExists("readelf", system))
        throw std::runtime_error("readelf requis mais introuvable (installez binutils)");
    if (resolver == "ldd" && !CommandExists("ldd", system))
        throw std::runtime_error("ldd requis mais introuvable");
    if (indexer == "nm" && !CommandExists("nm", system))
        throw std::runtime_error("nm requis mais introuvable (installez binutils)");

    return LibraryScannerFactory::Create(resolver, indexer);
}

std::vector<std::string> split_paths(const std::string& value, char sep) {
    std::vector<std::string> out;
    std::string current;
    for (char c : value) {
        if (c == sep) {
            out.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    out.push_back(current);
    return out;
}

std::vector<std::string> pathext_list(const SystemContext& system) {
#ifdef _WIN32
    std::string env_value = GetEnvValue(system, "PATHEXT");
    if (!env_value.empty()) {
        auto exts = split_paths(env_value, ';');
        if (!exts.empty())
            return exts;
    }
    return {".exe", ".bat", ".cmd"};
#else
    (void)system;
    return {""};
#endif
}

bool CommandExists(const std::string& cmd, const SystemContext& system) {
    if (cmd.empty() || !system.fs)
        return false;
    std::filesystem::path candidate(cmd);
    if (candidate.has_parent_path())
        return system.fs->IsExecutableFile(candidate);

    std::string path_env = GetEnvValue(system, "PATH");
    if (path_env.empty())
        return false;

#ifdef _WIN32
    const char sep = ';';
#else
    const char sep = ':';
#endif

    const auto paths = split_paths(path_env, sep);
    const auto exts = pathext_list(system);
    for (const auto& dir : paths) {
        if (dir.empty())
            continue;
        for (const auto& ext : exts) {
            std::filesystem::path probe = std::filesystem::path(dir) / (cmd + ext);
            if (system.fs->IsExecutableFile(probe))
                return true;
        }
    }
    return false;
}

std::string DetectArchFromBinary(const PipelineConfig& config, const SystemContext& system) {
    const std::string path = config.binary_path.Value();
    if (path.empty() || !system.shell)
        return "";
    try {
        std::string output = system.shell->Run("objdump -f " + ShellQuote(path));
        auto pos = output.find("architecture:");
        if (pos != std::string::npos) {
            auto rest = output.substr(pos + std::string("architecture:").size());
            auto end = rest.find(',');
            std::string arch = rest.substr(0, end);
            arch.erase(arch.find_last_not_of(" \t\r\n") + 1);
            arch.erase(0, arch.find_first_not_of(" \t\r\n"));
            return arch;
        }
    } catch (const std::exception&) {
    }
    return "";
}

}  // namespace

std::unique_ptr<PipelineRunner> PipelineFactory::BuildDefault(PipelineConfig config) {
    SystemContext system = DefaultSystemContext();

    if (!CommandExists("objdump", system))
        throw std::runtime_error("objdump requis mais introuvable (installez binutils)");

    auto reporter = ReporterFactory::Create(config);

    std::string arch = DetectArchFromBinary(config, system);
    auto analyzer = std::make_shared<CompositeInstructionAnalyzer>(
        arch.empty() ? InstructionAnalyzerFactory::CreateDefault(system)
                     : InstructionAnalyzerFactory::Create(arch));
    auto extractor = std::make_shared<BinaryExtractor>();
    auto hash_service = ChooseHashService(config, system);
    if (config.hash_algo.empty())
        config.hash_algo = hash_service.AlgorithmName();
    std::unique_ptr<IPartitioner> partitioner =
        std::make_unique<Partitioner>(config.binary_path, analyzer, extractor, hash_service);
    auto scanner = BuildScanner(config, system);
    auto hash_calc = std::make_shared<SummaryHashCalculator>(nullptr, hash_service);

    PhaseRegistry registry;
    registry.Register("disassembly", [&, system]() {
        return std::make_unique<TimingPhase>(std::make_unique<DisassemblyPhase>(
            DisassemblerFactory::Create(config, system)), reporter);
    });
    registry.Register("analysis", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<AnalysisPhase>(analyzer), reporter);
    });
    registry.Register("partitioning", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<PartitioningPhase>(
            std::make_unique<Partitioner>(config.binary_path, analyzer, extractor, hash_service),
            extractor), reporter);
    });
    registry.Register("artifacts", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<ArtifactsPhase>(
            std::make_unique<ArtifactBuilder>(config.output_dir.Value()),
            std::make_unique<SummaryWriter>(std::filesystem::path(config.output_dir.Value()), scanner, hash_calc),
            config.parallel_artifacts), reporter);
    });

    const std::vector<std::string> phase_names = {"disassembly", "analysis", "partitioning", "artifacts"};
    auto phases = registry.CreateSequence(phase_names);
    std::vector<PipelineRunner::PipelineStep> steps;
    steps.reserve(phases.size());
    steps.push_back({"disassembly", PipelineExit::DisassemblyError, std::move(phases[0])});
    steps.push_back({"analysis", PipelineExit::AnalysisError, std::move(phases[1])});
    steps.push_back({"partitioning", PipelineExit::PartitioningError, std::move(phases[2])});
    steps.push_back({"artifacts", PipelineExit::ArtifactsError, std::move(phases[3])});

    return std::make_unique<PipelineRunner>(std::move(config), std::move(steps), std::move(reporter));
}

}  // namespace splitter
