#include "pipeline/PipelineRunner.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string_view>
#include <vector>

#include "artifacts/FnvHashAlgorithm.hpp"
#include "artifacts/StdHashAlgorithm.hpp"
#include "pipeline/ConsoleReporter.hpp"
#include "pipeline/PipelineError.hpp"
#include "pipeline/PipelineFactory.hpp"
#include "support/Env.hpp"
#include "support/HashUtil.hpp"

namespace splitter {

namespace fs = std::filesystem;

namespace {

std::vector<PipelineRunner::PipelineStep> MakeDefaultSteps(
    std::unique_ptr<IPipelinePhase> disassembly,
    std::unique_ptr<IPipelinePhase> analysis,
    std::unique_ptr<IPipelinePhase> partitioning,
    std::unique_ptr<IPipelinePhase> artifacts) {
    std::vector<PipelineRunner::PipelineStep> steps;
    steps.reserve(4);
    steps.push_back({"disassembly", PipelineExit::DisassemblyError, std::move(disassembly)});
    steps.push_back({"analysis", PipelineExit::AnalysisError, std::move(analysis)});
    steps.push_back({"partitioning", PipelineExit::PartitioningError, std::move(partitioning)});
    steps.push_back({"artifacts", PipelineExit::ArtifactsError, std::move(artifacts)});
    return steps;
}

void PrintUsage(std::string_view prog) {
    std::cout << "Usage: " << prog << " <binary_file> [--output-dir <dir>] [--hash <fnv|std>] "
              << "[--resolver <ldd|readelf|pe>] [--indexer <nm|objdump|pe>] [--disassembler <objdump>] "
              << "[--reporter <console|json|ndjson>] [--report-file <path>]\n\n"
              << "Exemples:\n"
              << "  " << prog << " ./a.out\n"
              << "  " << prog << " program.exe --output-dir ./partitions --hash std\n\n"
              << "Necessite: objdump (and readelf/ldd for ELF paths)\n"
              << "Hash: variable d'environnement SPLITTER_HASH_ALGO ou option --hash.\n"
              << "D?sassembleur: env SPLITTER_DISASSEMBLER ou --disassembler (objdump).\n"
              << "R?solveur de biblioth?ques: env SPLITTER_LIB_RESOLVER ou --resolver (ldd/readelf/pe).\n"
              << "Indexation des symboles: env SPLITTER_SYMBOL_INDEXER ou --indexer (nm/objdump/pe).\n"
              << "Reporter: env SPLITTER_REPORTER ou --reporter (console/json/ndjson).\n";
}

}  // namespace

PipelineRunner::PipelineRunner(PipelineConfig config,
                               std::vector<PipelineStep> steps,
                               std::shared_ptr<IReporter> reporter)
    : context_(std::move(config)),
      steps_(std::move(steps)),
      reporter_(std::move(reporter)) {
    if (!reporter_)
        reporter_ = std::make_shared<ConsoleReporter>();
}

PipelineRunner::PipelineRunner(PipelineConfig config,
                               std::unique_ptr<IPipelinePhase> disassembly,
                               std::unique_ptr<IPipelinePhase> analysis,
                               std::unique_ptr<IPipelinePhase> partitioning,
                               std::unique_ptr<IPipelinePhase> artifacts,
                               std::shared_ptr<IReporter> reporter)
    : PipelineRunner(std::move(config),
                     MakeDefaultSteps(std::move(disassembly),
                                      std::move(analysis),
                                      std::move(partitioning),
                                      std::move(artifacts)),
                     std::move(reporter)) {}

int PipelineRunner::Run() {
    using clock = std::chrono::steady_clock;
    const auto run_start = clock::now();
    reporter_->ReportRunStart(context_.config.binary_path.Value(), context_.config.output_dir.Value());

    auto complete_run = [&](int exit_code) -> int {
        const auto run_ms = std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - run_start).count();
        reporter_->ReportRunCompleted(exit_code, run_ms);
        return exit_code;
    };

    for (auto& step : steps_) {
        if (step.key == "disassembly") {
            reporter_->Banner("=== D?sassemblage de " + context_.config.binary_path.Value() + " ===");
            if (!context_.config.hash_algo.empty())
                reporter_->Info("Hash: " + context_.config.hash_algo);
        } else if (step.key == "partitioning") {
            reporter_->Banner("=== Partitionnement du binaire ===");
        }

        if (!step.phase) {
            const int exit_code = static_cast<int>(step.on_error);
            std::cerr << "Erreur: phase '" << step.key << "' manquante.\n";
            reporter_->ReportPhaseFailed(step.key, {}, {}, 0, "missing phase implementation", exit_code);
            return complete_run(exit_code);
        }

        const auto phase_inputs = step.phase->Inputs();
        const auto phase_outputs = step.phase->Outputs();
        reporter_->ReportPhaseStart(step.key, phase_inputs, phase_outputs);
        const auto phase_start = clock::now();

        try {
            step.phase->Execute(context_);

            if (step.key == "disassembly") {
                reporter_->Info("Fonctions trouv?es: " + std::to_string(context_.functions.size()));
                PrintFunctionOverview(context_.functions);
                if (context_.config.dump_full_disassembly)
                    DumpDisassembly(context_.disassembly);
            } else if (step.key == "analysis") {
                ReportLoops(context_.functions);
            } else if (step.key == "partitioning") {
                reporter_->Info("Partitions cr??es: " + std::to_string(context_.partitions.size()));
                const std::size_t max_partitions =
                    []() {
                        if (auto env = GetEnv("SPLITTER_MAX_PARTITIONS"))
                            return static_cast<std::size_t>(std::stoull(*env));
                        return static_cast<std::size_t>(100000);
                    }();
                const std::size_t ratio_limit = 10;
                if (context_.partitions.size() > max_partitions
                    || context_.partitions.size() > context_.functions.size() * ratio_limit) {
                    std::ostringstream err;
                    err << "incoherent partition count: " << context_.partitions.size();
                    std::cerr << "Erreur: nombre de partitions incoh?rent (" << context_.partitions.size()
                              << "), abandon.\n";
                    const auto phase_ms =
                        std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - phase_start).count();
                    const int exit_code = static_cast<int>(PipelineExit::PartitioningError);
                    reporter_->ReportPhaseFailed(step.key, phase_inputs, phase_outputs, phase_ms, err.str(), exit_code);
                    return complete_run(exit_code);
                }

                for (const auto& partition : context_.partitions)
                    ReportPartition(partition);
            } else if (step.key == "artifacts") {
                reporter_->Banner("=== Termin? ===");
                reporter_->Info("Partitions: " + context_.config.output_dir.Value() + "/");
            }
        } catch (const PipelineError& e) {
            const auto phase_ms =
                std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - phase_start).count();
            const int exit_code = static_cast<int>(e.Code());
            std::cerr << "Erreur pendant " << step.phase->Name() << ": " << e.what() << "\n";
            reporter_->ReportPhaseFailed(step.key, phase_inputs, phase_outputs, phase_ms, e.what(), exit_code);
            return complete_run(exit_code);
        } catch (const std::exception& e) {
            const auto phase_ms =
                std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - phase_start).count();
            const int exit_code = static_cast<int>(step.on_error);
            std::cerr << "Erreur pendant " << step.phase->Name() << ": " << e.what() << "\n";
            reporter_->ReportPhaseFailed(step.key, phase_inputs, phase_outputs, phase_ms, e.what(), exit_code);
            return complete_run(exit_code);
        }

        const auto phase_ms =
            std::chrono::duration_cast<std::chrono::milliseconds>(clock::now() - phase_start).count();
        reporter_->ReportPhaseCompleted(step.key, phase_inputs, phase_outputs, phase_ms);
    }

    return complete_run(0);
}

void PipelineRunner::PrintFunctionOverview(const std::vector<Function>& functions) const {
    reporter_->Banner("=== Fonctions d?sassembl?es ===");
    reporter_->ReportFunctions(functions, context_.config.function_preview);
}

void PipelineRunner::DumpDisassembly(const std::string& disasm) const {
    fs::path out_dir(context_.config.output_dir.Value());
    fs::create_directories(out_dir);
    const fs::path path = out_dir / "disassembly_full.asm";
    std::ofstream full_asm(path);
    full_asm << disasm;
    reporter_->Info("D?sassemblage complet: " + path.string());
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
        } else if (current == "--disassembler" && i + 1 < args.size()) {
            config.disassembler = std::string(args[++i]);  // objdump
        } else if (current == "--reporter" && i + 1 < args.size()) {
            config.reporter = std::string(args[++i]);  // console/json
        } else if (current == "--report-file" && i + 1 < args.size()) {
            config.report_file = std::string(args[++i]);
        }
    }

    auto runner = PipelineFactory::BuildDefault(std::move(config));
    return runner->Run();
}

}  // namespace splitter
