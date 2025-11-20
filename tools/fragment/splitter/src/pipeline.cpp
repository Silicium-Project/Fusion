#include "splitter/pipeline.hpp"

#include <algorithm>
#include <filesystem>
#include <functional>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string_view>
#include <vector>

#include <future>

#include "splitter/instruction_analysis.hpp"

namespace splitter {

    namespace fs = std::filesystem;

    namespace {

        template <typename Container>
        void print_sample(const std::string& label, const Container& container, std::size_t limit) {
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

        void print_usage(std::string_view prog) {
            std::cout << "Usage: " << prog << " <binary_file> [--output-dir <dir>]\n\n"
                    << "Exemples:\n"
                    << "  " << prog << " ./a.out\n"
                    << "  " << prog << " program.exe --output-dir ./partitions\n\n"
                    << "Nécessite: objdump, readelf (binutils)\n";
        }

    }  // namespace

    PipelineRunner::PipelineRunner(PipelineConfig config,
                                   std::unique_ptr<Disassembler> disassembler,
                                   std::unique_ptr<Partitioner> partitioner,
                                   std::unique_ptr<ArtifactBuilder> artifact_builder)
    : config_(std::move(config))
    , disassembler_(disassembler ? std::move(disassembler)
                                 : std::make_unique<Disassembler>(config_.binary_path))
    , partitioner_(partitioner ? std::move(partitioner)
                               : std::make_unique<Partitioner>(config_.binary_path))
    , artifact_builder_(artifact_builder ? std::move(artifact_builder)
                                         : std::make_unique<ArtifactBuilder>(config_.output_dir)) {}

    int PipelineRunner::run() {
        std::cout << "=== Désassemblage de " << config_.binary_path << " ===\n\n";

        std::vector<Function> functions;
        std::string disasm_full;

        try {
            auto result = disassembler_->run();
            functions = std::move(result.first);
            disasm_full = std::move(result.second);
        } catch (const std::exception& e) {
            std::cerr << "Erreur: " << e.what() << "\n";
            return 1;
        }

        std::cout << "Fonctions trouvées: " << functions.size() << "\n\n";
        print_function_overview(functions);
        if (config_.dump_full_disassembly)
            dump_disassembly(disasm_full);
        report_loops(functions);

        std::cout << "\n=== Partitionnement du binaire ===\n\n";
        auto partitions = partitioner_->run(functions);
        std::cout << "Partitions créées: " << partitions.size() << "\n";

        std::vector<PartitionFiles> generated_files;
        generated_files.reserve(partitions.size());

        if (config_.parallel_artifacts) {
            std::vector<std::future<PartitionFiles>> futures;
            futures.reserve(partitions.size());
            for (const auto& partition : partitions) {
                report_partition(partition);
                futures.emplace_back(std::async(std::launch::async, [&builder = *artifact_builder_, &partition]() {
                    return builder.create_partition(partition);
                }));
            }
            for (auto& future : futures)
                generated_files.push_back(future.get());
        } else {
            for (const auto& partition : partitions) {
                report_partition(partition);
                generated_files.push_back(artifact_builder_->create_partition(partition));
            }
        }

        auto memory_segments = extract_data_sections(config_.binary_path);
        artifact_builder_->write_summary(partitions, generated_files, memory_segments, config_.binary_path);
        std::cout << "\n=== Terminé ===\n";
        std::cout << "\nPartitions: " << config_.output_dir << "/\n";
        return 0;
    }

    void PipelineRunner::print_function_overview(const std::vector<Function>& functions) const {
        std::cout << "=== Fonctions désassemblées ===\n\n";
        const size_t preview = std::min(config_.function_preview, functions.size());
        for (size_t i = 0; i < preview; ++i) {
            const auto& func = functions[i];
            uint64_t size = func.end_addr - func.start_addr;
            std::cout << "  " << std::left << std::setw(30) << func.name
                      << " @ 0x" << std::hex << std::setw(10) << func.start_addr
                      << std::dec << " (" << std::setw(4) << func.instructions.size()
                      << " insts, " << std::setw(5) << size << " bytes)\n";
        }
        if (functions.size() > preview)
            std::cout << "  ... (" << (functions.size() - preview) << " autres fonctions)\n";
    }

    void PipelineRunner::dump_disassembly(const std::string& disasm) const {
        fs::create_directories(config_.output_dir);
        const std::string path = config_.output_dir + "/disassembly_full.asm";
        std::ofstream full_asm(path);
        full_asm << disasm;
        std::cout << "\nDésassemblage complet: " << path << "\n";
    }

    void PipelineRunner::report_loops(std::vector<Function>& functions) const {
        std::cout << "\n=== Analyse des boucles ===\n\n";
        std::vector<std::reference_wrapper<Function>> loop_functions;
        for (auto& func : functions)
            if (analyze_function_loops(func))
                loop_functions.push_back(func);

        std::cout << "Fonctions avec boucles: " << loop_functions.size() << "\n\n";
        const size_t preview = std::min(config_.loop_preview, loop_functions.size());
        for (size_t i = 0; i < preview; ++i) {
            const auto& func = loop_functions[i].get();
            auto loop_info = detect_loop_patterns(func);
            std::string status = loop_info.parallelizable ?
                                 "PARALLÉLISABLE" : "SÉQUENTIELLE";
            std::cout << "  " << std::left << std::setw(30) << func.name
                      << " - " << status << "\n";
            if (!loop_info.reason.empty())
                std::cout << "    Raison: " << loop_info.reason << "\n";
        }
    }

    void PipelineRunner::report_partition(const BinaryPartition& partition) const {
        std::string status = partition.is_parallelizable ? "PARALLÈLE" : "SÉQUENTIEL";
        std::cout << "\nPartition: " << partition.id << " (" << status << ")\n";
        std::cout << "  Adresse: 0x" << std::hex << partition.start_addr
                  << " - 0x" << partition.end_addr << std::dec << "\n";
        std::cout << "  Taille: " << partition.raw_bytes.size() << " bytes\n";

        const auto limit = config_.sample_preview;
        print_sample("Inputs", partition.inputs, limit);
        print_sample("Inputs externes", partition.external_inputs, limit);
        print_sample("Outputs", partition.outputs, limit);
    }

    int run_cli(const std::vector<std::string_view>& args) {
        if (args.size() < 2) {
            std::string_view prog = args.empty() ? "splitter" : args.front();
            print_usage(prog);
            return 1;
        }

        PipelineConfig config;
        config.binary_path = std::string(args[1]);

        for (size_t i = 2; i < args.size(); ++i) {
            std::string current(args[i]);
            if (current == "--output-dir" && i + 1 < args.size())
                config.output_dir = std::string(args[++i]);
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
        }

        PipelineRunner runner(std::move(config));
        return runner.run();
    }

}  // namespace splitter
