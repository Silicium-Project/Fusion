#include "splitter/artifacts.hpp"

#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>

#include "splitter/util.hpp"

namespace splitter {

namespace fs = std::filesystem;

PartitionFiles create_standalone_partition(const BinaryPartition& partition,
                                           const std::string& output_dir) {
    fs::create_directories(output_dir);

    PartitionFiles files;
    files.asm_file = output_dir + "/" + partition.id + ".asm";
    files.bin_file = output_dir + "/" + partition.id + ".bin";
    files.wrapper_file = output_dir + "/" + partition.id + "_wrapper.c";

    std::ofstream asm_out(files.asm_file);
    asm_out << partition.asm_code;
    asm_out.close();

    std::ofstream bin_out(files.bin_file, std::ios::binary);
    bin_out.write(reinterpret_cast<const char*>(partition.raw_bytes.data()),
                  static_cast<std::streamsize>(partition.raw_bytes.size()));
    bin_out.close();

    std::ofstream wrapper_out(files.wrapper_file);
    wrapper_out << "// Wrapper pour partition: " << partition.id << "\n"
                << "#include <stdio.h>\n"
                << "#include <stdint.h>\n\n"
                << "extern void partition_code();\n\n"
                << "int main() {\n"
                << "    printf(\"Exécution partition: " << partition.id << "\\n\");\n"
                << "    // partition_code();\n"
                << "    return 0;\n"
                << "}\n";
    wrapper_out.close();

    return files;
}

void write_summary(const std::vector<BinaryPartition>& partitions,
                   const std::vector<PartitionFiles>& artifacts,
                   const std::string& output_dir,
                   const std::string& binary_path) {
    std::string summary_path = output_dir + "/summary.json";
    std::ofstream summary_out(summary_path);
    if (!summary_out) {
        std::cerr << "Avertissement: impossible d'écrire " << summary_path << "\n";
        return;
    }

    size_t parallelizable_count = 0;
    for (const auto& partition : partitions) {
        if (partition.is_parallelizable) {
            ++parallelizable_count;
        }
    }

    summary_out << "{\n";
    summary_out << "  \"binary\": \"" << json_escape(binary_path) << "\",\n";
    summary_out << "  \"partitions_count\": " << partitions.size() << ",\n";
    summary_out << "  \"parallelizable_count\": " << parallelizable_count << ",\n";
    summary_out << "  \"partitions\": [\n";

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        const auto& partition = partitions[idx];
        summary_out << "    {\n";
        summary_out << "      \"id\": \"" << json_escape(partition.id) << "\",\n";
        summary_out << "      \"start\": \"0x" << std::hex << partition.start_addr
                    << std::dec << "\",\n";
        summary_out << "      \"end\": \"0x" << std::hex << partition.end_addr
                    << std::dec << "\",\n";
        summary_out << "      \"size\": " << partition.raw_bytes.size() << ",\n";
        summary_out << "      \"parallelizable\": "
                    << (partition.is_parallelizable ? "true" : "false") << ",\n";
        summary_out << "      \"inputs\": " << set_to_json(partition.inputs) << ",\n";
        summary_out << "      \"external_inputs\": "
                    << set_to_json(partition.external_inputs) << ",\n";
        summary_out << "      \"outputs\": " << set_to_json(partition.outputs) << ",\n";
        summary_out << "      \"parents\": " << vector_to_json(partition.parents) << ",\n";
        summary_out << "      \"dependencies\": " << vector_to_json(partition.dependencies)
                    << ",\n";
        summary_out << "      \"unresolved_calls\": "
                    << vector_to_json(partition.unresolved_dependencies) << ",\n";
        if (idx < artifacts.size()) {
            summary_out << "      \"asm\": \"" << json_escape(artifacts[idx].asm_file)
                        << "\",\n";
            summary_out << "      \"bin\": \"" << json_escape(artifacts[idx].bin_file)
                        << "\",\n";
            summary_out << "      \"wrapper\": \"" << json_escape(artifacts[idx].wrapper_file)
                        << "\"\n";
        } else {
            summary_out << "      \"asm\": \"\",\n";
            summary_out << "      \"bin\": \"\",\n";
            summary_out << "      \"wrapper\": \"\"\n";
        }
        summary_out << "    }";
        if (idx + 1 < partitions.size()) {
            summary_out << ",";
        }
        summary_out << "\n";
    }
    summary_out << "  ]\n";
    summary_out << "}\n";

    summary_out.close();
    std::cout << "\nRésumé: " << summary_path << "\n";
}

}  // namespace splitter
