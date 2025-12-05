#include "pipeline/PipelineRunner.hpp"

#include <algorithm>
#include <chrono>
#include <filesystem>
#include <cstdlib>
#include <functional>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string_view>
#include <vector>

#include "analysis/X86_64InstructionAnalyzer.hpp"
#include "analysis/ObjdumpDisassembler.hpp"
#include "artifacts/ArtifactBuilder.hpp"
#include "artifacts/SummaryWriter.hpp"
#include "pipeline/AnalysisPhase.hpp"
#include "pipeline/ArtifactsPhase.hpp"
#include "pipeline/DisassemblyPhase.hpp"
#include "pipeline/ConsoleReporter.hpp"
#include "pipeline/JsonReporter.hpp"
#include "pipeline/PartitioningPhase.hpp"
#include "pipeline/PipelineError.hpp"
#include "pipeline/PipelineFactory.hpp"
#include "partitioning/Partitioner.hpp"
#include "support/HashUtil.hpp"
#include "support/Env.hpp"
#include "artifacts/FnvHashAlgorithm.hpp"
#include "artifacts/StdHashAlgorithm.hpp"

namespace splitter {

namespace fs = std::filesystem;

namespace {

template <typename Container>
void PrintSample(const std::string& label, const Container& container, std::size_t limit) {
    std::cout << "  " << label << ": ";
    size_t count = 0;
    for (const auto& item : container) {
        if (count++ >= limit) {
            std::cout << "...";
            break;
        }
        std::cout << item << " ";
    }
    std::cout << "\n";
}

void PrintUsage(std::string_view prog) {
    std::cout << "Usage: " << prog << " <binary_file> [--output-dir <dir>] [--hash <fnv|std>] "
              << "[--resolver <ldd|readelf>] [--indexer <nm|objdump>] [--reporter <console|json>]\n\n"
              << "Exemples:\n"
              << "  " << prog << " ./a.out\n"
              << "  " << prog << " program.exe --output-dir ./partitions --hash std\n\n"
              << "Nécessite: objdump, readelf (binutils)\n"
              << "Hash: variable d'environnement SPLITTER_HASH_ALGO ou option --hash.\n"
              << "Résolveur de bibliothèques: env SPLITTER_LIB_RESOLVER ou --resolver (ldd/readelf).\n"
              << "Indexation des symboles: env SPLITTER_SYMBOL_INDEXER ou --indexer (nm/objdump).\n"
              << "Reporter: env SPLITTER_REPORTER ou --reporter (console/json).\n";
}

}  // namespace

PipelineRunner::PipelineRunner(PipelineConfig config,
                               std::unique_ptr<IPipelinePhase> disassembly,
                               std::unique_ptr<IPipelinePhase> analysis,
                               std::unique_ptr<IPipelinePhase> partitioning,
                               std::unique_ptr<IPipelinePhase> artifacts,
                               std::unique_ptr<IReporter> reporter)
    : context_(std::move(config)),
      disassembly_(std::move(disassembly)),
      analysis_(std::move(analysis)),
      partitioning_(std::move(partitioning)),
      artifacts_(std::move(artifacts)),
      reporter_(std::move(reporter)) {
    if (!reporter_)
        reporter_ = std::make_unique<ConsoleReporter>();
}

int PipelineRunner::Run() {
    reporter_->Banner("=== Désassemblage de " + context_.config.binary_path.Value() + " ===");
    int exit_code = 0;
    auto run_phase = [&](std::unique_ptr<IPipelinePhase>& phase, PipelineExit code) -> bool {
        try {
            phase->Execute(context_);
        } catch (const PipelineError& e) {
            std::cerr << "Erreur pendant " << phase->Name() << ": " << e.what() << "\n";
            exit_code = static_cast<int>(e.Code());
            return false;
        } catch (const std::exception& e) {
            std::cerr << "Erreur pendant " << phase->Name() << ": " << e.what() << "\n";
            exit_code = static_cast<int>(code);
            return false;
        }
        return true;
    };

    if (!run_phase(disassembly_, PipelineExit::DisassemblyError))
        return exit_code ? exit_code : static_cast<int>(PipelineExit::DisassemblyError);

    reporter_->Info("Fonctions trouvées: " + std::to_string(context_.functions.size()));
    PrintFunctionOverview(context_.functions);
    if (context_.config.dump_full_disassembly)
        DumpDisassembly(context_.disassembly);

    if (!run_phase(analysis_, PipelineExit::AnalysisError))
        return exit_code ? exit_code : static_cast<int>(PipelineExit::AnalysisError);
    ReportLoops(context_.functions);

    reporter_->Banner("=== Partitionnement du binaire ===");
    if (!run_phase(partitioning_, PipelineExit::PartitioningError))
        return exit_code ? exit_code : static_cast<int>(PipelineExit::PartitioningError);
    reporter_->Info("Partitions créées: " + std::to_string(context_.partitions.size()));
    const std::size_t max_partitions =
        []() {
            if (auto env = GetEnv("SPLITTER_MAX_PARTITIONS"))
                return static_cast<std::size_t>(std::stoull(*env));
            return static_cast<std::size_t>(100000);
        }();
    const std::size_t ratio_limit = 10;
    if (context_.partitions.size() > max_partitions
        || context_.partitions.size() > context_.functions.size() * ratio_limit) {
        std::cerr << "Erreur: nombre de partitions incohérent (" << context_.partitions.size()
                  << "), abandon.\n";
        return static_cast<int>(PipelineExit::PartitioningError);
    }

    for (const auto& partition : context_.partitions)
        ReportPartition(partition);

    if (!run_phase(artifacts_, PipelineExit::ArtifactsError))
        return exit_code ? exit_code : static_cast<int>(PipelineExit::ArtifactsError);
    reporter_->Banner("=== Terminé ===");
    reporter_->Info("Partitions: " + context_.config.output_dir.Value() + "/");
    return 0;
}

void PipelineRunner::PrintFunctionOverview(const std::vector<Function>& functions) const {
    reporter_->Banner("=== Fonctions désassemblées ===");
    reporter_->ReportFunctions(functions, context_.config.function_preview);
}

void PipelineRunner::DumpDisassembly(const std::string& disasm) const {
    fs::path out_dir(context_.config.output_dir.Value());
    fs::create_directories(out_dir);
    const fs::path path = out_dir / "disassembly_full.asm";
    std::ofstream full_asm(path);
    full_asm << disasm;
    reporter_->Info("Désassemblage complet: " + path.string());
}

void PipelineRunner::ReportLoops(std::vector<Function>& functions) const {
    reporter_->Banner("=== Analyse des boucles ===");
    reporter_->ReportLoops(functions, context_.config.loop_preview);
}

void PipelineRunner::ReportPartition(const Partition& partition) const {
    reporter_->ReportPartition(partition, context_.config.sample_preview);
}

int RunCli(const std::vector<std::string_view>& args) {
    if (args.size() < 2) {
        std::string_view prog = args.empty() ? "splitter" : args.front();
        PrintUsage(prog);
        return 1;
    }

    PipelineConfig config;
    config.binary_path = BinaryPath(std::string(args[1]));

    for (size_t i = 2; i < args.size(); ++i) {
        std::string current(args[i]);
        if (current == "--output-dir" && i + 1 < args.size())
            config.output_dir = OutputDir(std::string(args[++i]));
        else if (current == "--function-preview" && i + 1 < args.size())
            config.function_preview = static_cast<std::size_t>(std::stoul(std::string(args[++i])));
        else if (current == "--loop-preview" && i + 1 < args.size())
            config.loop_preview = static_cast<std::size_t>(std::stoul(std::string(args[++i])));
        else if (current == "--sample-preview" && i + 1 < args.size())
            config.sample_preview = static_cast<std::size_t>(std::stoul(std::string(args[++i])));
        else if (current == "--no-disassembly")
            config.dump_full_disassembly = false;
        else if (current == "--parallel-artifacts")
            config.parallel_artifacts = true;
        else if (current == "--hash" && i + 1 < args.size()) {
            std::string algo(args[++i]);
            if (algo == "std")
                SetGlobalHashService(HashService(std::make_shared<StdHashAlgorithm>()));
            else
                SetGlobalHashService(HashService(std::make_shared<FnvHashAlgorithm>()));
            config.hash_algo = algo;
        } else if (current == "--resolver" && i + 1 < args.size()) {
            config.resolver = std::string(args[++i]);  // ldd/readelf/auto
        } else if (current == "--indexer" && i + 1 < args.size()) {
            config.symbol_indexer = std::string(args[++i]);  // nm/objdump/auto
        } else if (current == "--reporter" && i + 1 < args.size()) {
            config.reporter = std::string(args[++i]);  // console/json
        }
    }

    auto runner = PipelineFactory::BuildDefault(std::move(config));
    return runner->Run();
}

}  // namespace splitter
