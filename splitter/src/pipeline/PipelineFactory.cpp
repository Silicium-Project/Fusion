#include "pipeline/PipelineFactory.hpp"

#include <algorithm>
#include <cstdlib>
#include <memory>
#include <filesystem>

#include "analysis/ObjdumpDisassembler.hpp"
#include "analysis/CompositeInstructionAnalyzer.hpp"
#include "analysis/InstructionAnalyzerFactory.hpp"
#include "artifacts/ArtifactBuilder.hpp"
#include "artifacts/LibraryScanner.hpp"
#include "artifacts/SummaryWriter.hpp"
#include "partitioning/BinaryExtractor.hpp"
#include "partitioning/Partitioner.hpp"
#include "pipeline/AnalysisPhase.hpp"
#include "pipeline/ArtifactsPhase.hpp"
#include "pipeline/DisassemblyPhase.hpp"
#include "pipeline/ReporterFactory.hpp"
#include "pipeline/PartitioningPhase.hpp"
#include "pipeline/PhaseRegistry.hpp"
#include "pipeline/TimingPhase.hpp"
#include "support/HashService.hpp"
#include "support/Env.hpp"
#include "artifacts/LibraryScannerFactory.hpp"
#include "artifacts/HashAlgorithmFactory.hpp"
#include "support/ShellCommand.hpp"

namespace splitter {

namespace {

bool CommandExists(const std::string& cmd);

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

    if (resolver == "readelf" && !CommandExists("readelf"))
        throw std::runtime_error("readelf requis mais introuvable (installez binutils)");
    if (resolver == "ldd" && !CommandExists("ldd"))
        throw std::runtime_error("ldd requis mais introuvable");
    if (indexer == "nm" && !CommandExists("nm"))
        throw std::runtime_error("nm requis mais introuvable (installez binutils)");

    return LibraryScannerFactory::Create(resolver, indexer);
}

bool is_executable_file(const std::filesystem::path& path) {
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec))
        return false;
#ifdef _WIN32
    (void)ec;
    return true;
#else
    auto perms = std::filesystem::status(path, ec).permissions();
    if (ec)
        return false;
    using perms = std::filesystem::perms;
    return (perms & perms::owner_exec) != perms::none
        || (perms & perms::group_exec) != perms::none
        || (perms & perms::others_exec) != perms::none;
#endif
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

std::vector<std::string> pathext_list() {
#ifdef _WIN32
    if (auto env = GetEnv("PATHEXT")) {
        auto exts = split_paths(*env, ';');
        if (!exts.empty())
            return exts;
    }
    return {".exe", ".bat", ".cmd"};
#else
    return {""};
#endif
}

bool CommandExists(const std::string& cmd) {
    if (cmd.empty())
        return false;
    std::filesystem::path candidate(cmd);
    if (candidate.has_parent_path())
        return is_executable_file(candidate);

    std::string path_env;
    if (auto env = GetEnv("PATH"))
        path_env = *env;
    if (path_env.empty())
        return false;

#ifdef _WIN32
    const char sep = ';';
#else
    const char sep = ':';
#endif

    const auto paths = split_paths(path_env, sep);
    const auto exts = pathext_list();
    for (const auto& dir : paths) {
        if (dir.empty())
            continue;
        for (const auto& ext : exts) {
            std::filesystem::path probe = std::filesystem::path(dir) / (cmd + ext);
            if (is_executable_file(probe))
                return true;
        }
    }
    return false;
}

std::string DetectArchFromBinary(const PipelineConfig& config) {
    const std::string path = config.binary_path.Value();
    if (path.empty())
        return "";
    try {
        std::string output = ExecCommand("objdump -f " + ShellQuote(path));
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
    if (!CommandExists("objdump"))
        throw std::runtime_error("objdump requis mais introuvable (installez binutils)");

    auto reporter = ReporterFactory::Create(config);
    auto disassembly = std::make_unique<DisassemblyPhase>(
        std::make_unique<ObjdumpDisassembler>(config.binary_path.Value()));

    std::string arch = DetectArchFromBinary(config);
    auto analyzer = std::make_shared<CompositeInstructionAnalyzer>(
        arch.empty() ? InstructionAnalyzerFactory::CreateDefault()
                     : InstructionAnalyzerFactory::Create(arch));
    auto analysis = std::make_unique<AnalysisPhase>(analyzer);

    auto extractor = std::make_shared<BinaryExtractor>();
    auto hash_service = ChooseHashService(config);
    if (config.hash_algo.empty())
        config.hash_algo = hash_service.AlgorithmName();
    std::unique_ptr<IPartitioner> partitioner =
        std::make_unique<Partitioner>(config.binary_path, analyzer, extractor, hash_service);
    auto partitioning = std::make_unique<PartitioningPhase>(std::move(partitioner), extractor);

    auto scanner = BuildScanner(config);
    auto hash_calc = std::make_shared<SummaryHashCalculator>(nullptr, hash_service);
    auto artifacts_builder = std::make_unique<ArtifactBuilder>(config.output_dir.Value());
    auto summary_writer =
        std::make_unique<SummaryWriter>(std::filesystem::path(config.output_dir.Value()), scanner, hash_calc);

    PhaseRegistry registry;
    registry.Register("disassembly", [&]() {
        return std::make_unique<TimingPhase>(std::make_unique<DisassemblyPhase>(
            std::make_unique<ObjdumpDisassembler>(config.binary_path.Value())), reporter);
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

    auto phases = registry.CreateSequence({"disassembly", "analysis", "partitioning", "artifacts"});

    return std::make_unique<PipelineRunner>(std::move(config), std::move(phases[0]),
                                            std::move(phases[1]), std::move(phases[2]),
                                            std::move(phases[3]), std::move(reporter));
}

}  // namespace splitter
