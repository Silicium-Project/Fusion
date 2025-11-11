#include "splitter/pipeline.hpp"

#include <filesystem>
#include <functional>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string_view>
#include <vector>

#include "splitter/artifacts.hpp"
#include "splitter/disassembly.hpp"
#include "splitter/instruction_analysis.hpp"
#include "splitter/partitioner.hpp"
#include "splitter/types.hpp"

namespace splitter {

    namespace fs = std::filesystem;

    template <typename Container>
    static void print_sample(const std::string& label, const Container& container) {
        std::cout << "  " << label << ": ";
        size_t count = 0;
        for (const auto& item : container) {
            if (count++ >= 5) {
                std::cout << "...";
                break;
            }
            std::cout << item << " ";
        }
        std::cout << "\n";
    }

    static void print_usage(std::string_view prog) {
        std::cout << "Usage: " << prog << " <binary_file> [--output-dir <dir>]\n\n"
                << "Exemples:\n"
                << "  " << prog << " ./a.out\n"
                << "  " << prog << " program.exe --output-dir ./partitions\n\n"
                << "Nécessite: objdump, readelf (binutils)\n";
    }

    static void print_function_overview(const std::vector<Function>& functions) {
        std::cout << "=== Fonctions désassemblées ===\n\n";
        const size_t preview = std::min<size_t>(20, functions.size());
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

    static void dump_disassembly(const std::string& disasm) {
        std::ofstream full_asm("disassembly_full.asm");
        full_asm << disasm;
        std::cout << "\nDésassemblage complet: disassembly_full.asm\n";
    }

    static void report_loops(std::vector<Function>& functions) {
        std::cout << "\n=== Analyse des boucles ===\n\n";
        std::vector<std::reference_wrapper<Function>> loop_functions;
        for (auto& func : functions)
            if (analyze_function_loops(func))
                loop_functions.push_back(func);

        std::cout << "Fonctions avec boucles: " << loop_functions.size() << "\n\n";
        const size_t preview = std::min<size_t>(10, loop_functions.size());
        for (size_t i = 0; i < preview; ++i) {
            const auto& func = loop_functions[i].get();
            auto loop_info = detect_loop_patterns(func);
            std::string status = (loop_info["parallelizable"] == "true") ?
                                "PARALLÉLISABLE" : "SÉQUENTIELLE";
            std::cout << "  " << std::left << std::setw(30) << func.name
                    << " - " << status << "\n";
            if (loop_info.count("reason"))
                std::cout << "    Raison: " << loop_info["reason"] << "\n";
        }
    }

    static void report_partition(const BinaryPartition& partition) {
        std::string status = partition.is_parallelizable ? "PARALLÈLE" : "SÉQUENTIEL";
        std::cout << "\nPartition: " << partition.id << " (" << status << ")\n";
        std::cout << "  Adresse: 0x" << std::hex << partition.start_addr
                << " - 0x" << partition.end_addr << std::dec << "\n";
        std::cout << "  Taille: " << partition.raw_bytes.size() << " bytes\n";

        print_sample("Inputs", partition.inputs);
        print_sample("Inputs externes", partition.external_inputs);
        print_sample("Outputs", partition.outputs);
    }

    int run_cli(const std::vector<std::string_view>& args) {
        if (args.size() < 2) {
            std::string_view prog = args.empty() ? "splitter" : args.front();
            print_usage(prog);
            return 1;
        }

        std::string binary_path = std::string(args[1]);
        std::string output_dir = "./partitions";

        for (size_t i = 2; i < args.size(); ++i)
            if (std::string(args[i]) == "--output-dir" && i + 1 < args.size()) {
                output_dir = std::string(args[++i]);
            }

        std::cout << "=== Désassemblage de " << binary_path << " ===\n\n";

        std::vector<Function> functions;
        std::string disasm_full;

        try {
            auto result = disassemble_binary(binary_path);
            functions = std::move(result.first);
            disasm_full = std::move(result.second);
        } catch (const std::exception& e) {
            std::cerr << "Erreur: " << e.what() << "\n";
            return 1;
        }

        std::cout << "Fonctions trouvées: " << functions.size() << "\n\n";
        print_function_overview(functions);
        dump_disassembly(disasm_full);
        report_loops(functions);

        std::cout << "\n=== Partitionnement du binaire ===\n\n";
        auto partitions = partition_binary(functions, binary_path);
        std::cout << "Partitions créées: " << partitions.size() << "\n";

        fs::create_directories(output_dir);
        std::vector<PartitionFiles> generated_files;
        generated_files.reserve(partitions.size());

        for (const auto& partition : partitions) {
            report_partition(partition);
            generated_files.push_back(create_standalone_partition(partition, output_dir));
        }

        write_summary(partitions, generated_files, output_dir, binary_path);
        std::cout << "\n=== Terminé ===\n";
        std::cout << "\nPartitions: " << output_dir << "/\n";
        return 0;
    }

}  // namespace splitter
