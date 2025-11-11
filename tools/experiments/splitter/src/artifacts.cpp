#include "splitter/artifacts.hpp"

#include <filesystem>
#include <functional>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>

#include "splitter/util.hpp"

namespace splitter {

    namespace fs = std::filesystem;

    static void write_text_file(const std::string& path, const std::string& content) {
        std::ofstream file(path);
        file << content;
    }

    static void write_binary_file(const std::string& path, const std::vector<uint8_t>& data) {
        std::ofstream file(path, std::ios::binary);
        std::vector<char> buffer(data.begin(), data.end());
        file.write(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    }

    static void write_wrapper_skeleton(const std::string& path, const std::string& partition_id) {
        std::ofstream wrapper(path);
        wrapper << "// Wrapper pour partition: " << partition_id << "\n"
                << "#include <stdio.h>\n"
                << "#include <stdint.h>\n\n"
                << "extern void partition_code();\n\n"
                << "int main() {\n"
                << "    printf(\"Exécution partition: " << partition_id << "\\n\");\n"
                << "    // partition_code();\n"
                << "    return 0;\n"
                << "}\n";
    }

    static size_t count_parallelizable(const std::vector<BinaryPartition>& partitions) {
        size_t count = 0;

        for (const auto& partition : partitions)
            if (partition.is_parallelizable)
                ++count;
        return count;
    }

    static std::string hex_string(uint64_t value) {
        std::ostringstream oss;
        oss << "0x" << std::hex << value;

        return oss.str();
    }

    static std::optional<std::reference_wrapper<const PartitionFiles>> artifact_for(
            size_t idx, const std::vector<PartitionFiles>& artifacts) {

        if (idx >= artifacts.size())
            return std::nullopt;
        return std::cref(artifacts[idx]);
    }

    static void write_partition_entry(std::ofstream& out,
            const BinaryPartition& partition,
            const std::optional<std::reference_wrapper<const PartitionFiles>>& files,
            bool is_last) {

        out << "    {\n";
        out << "      \"id\": \"" << json_escape(partition.id) << "\",\n";
        out << "      \"start\": \"" << hex_string(partition.start_addr) << "\",\n";
        out << "      \"end\": \"" << hex_string(partition.end_addr) << "\",\n";
        out << "      \"size\": " << partition.raw_bytes.size() << ",\n";
        out << "      \"parallelizable\": "
            << (partition.is_parallelizable ? "true" : "false") << ",\n";
        out << "      \"inputs\": " << set_to_json(partition.inputs) << ",\n";
        out << "      \"external_inputs\": "
            << set_to_json(partition.external_inputs) << ",\n";
        out << "      \"outputs\": " << set_to_json(partition.outputs) << ",\n";
        out << "      \"parents\": " << vector_to_json(partition.parents) << ",\n";
        out << "      \"dependencies\": " << vector_to_json(partition.dependencies) << ",\n";
        out << "      \"unresolved_calls\": "
            << vector_to_json(partition.unresolved_dependencies) << ",\n";

        if (files.has_value()) {
            const auto& part_files = files->get();
            out << "      \"asm\": \"" << json_escape(part_files.asm_file) << "\",\n";
            out << "      \"bin\": \"" << json_escape(part_files.bin_file) << "\",\n";
            out << "      \"wrapper\": \"" << json_escape(part_files.wrapper_file) << "\"\n";
        } else {
            out << "      \"asm\": \"\",\n";
            out << "      \"bin\": \"\",\n";
            out << "      \"wrapper\": \"\"\n";
        }

        out << "    }";
        if (!is_last)
            out << ",";
        out << "\n";
    }

    static bool open_summary_file(const std::string& path, std::ofstream& out) {
        out.open(path);
        if (out)
            return true;
        std::cerr << "Avertissement: impossible d'écrire " << path << "\n";
        return false;
    }

    static void write_summary_header(std::ofstream& out, const std::string& binary_path,
                                    size_t partition_count, size_t parallelizable_count) {

        out << "{\n";
        out << "  \"binary\": \"" << json_escape(binary_path) << "\",\n";
        out << "  \"partitions_count\": " << partition_count << ",\n";
        out << "  \"parallelizable_count\": " << parallelizable_count << ",\n";
        out << "  \"partitions\": [\n";
    }

    static void write_summary_footer(std::ofstream& out) {
        out << "  ]\n";
        out << "}\n";
    }

    static void write_partitions_block(std::ofstream& out,
            const std::vector<BinaryPartition>& partitions,
            const std::vector<PartitionFiles>& artifacts) {

        for (size_t idx = 0; idx < partitions.size(); ++idx) {
            const bool is_last = (idx + 1 == partitions.size());
            write_partition_entry(out, partitions[idx], artifact_for(idx, artifacts), is_last);
        }
    }

    PartitionFiles create_standalone_partition(const BinaryPartition& partition,
                                            const std::string& output_dir) {
        fs::create_directories(output_dir);

            PartitionFiles files;
            files.asm_file = output_dir + "/" + partition.id + ".asm";
            files.bin_file = output_dir + "/" + partition.id + ".bin";
            files.wrapper_file = output_dir + "/" + partition.id + "_wrapper.c";

            write_text_file(files.asm_file, partition.asm_code);
            write_binary_file(files.bin_file, partition.raw_bytes);
            write_wrapper_skeleton(files.wrapper_file, partition.id);

            return files;
        }

    void write_summary(const std::vector<BinaryPartition>& partitions,
                    const std::vector<PartitionFiles>& artifacts,
                    const std::string& output_dir,
                    const std::string& binary_path) {

        std::string summary_path = output_dir + "/summary.json";
        std::ofstream summary;

        if (!open_summary_file(summary_path, summary))
            return;

        write_summary_header(summary, binary_path, partitions.size(), count_parallelizable(partitions));
        write_partitions_block(summary, partitions, artifacts);
        write_summary_footer(summary);

        std::cout << "\nRésumé: " << summary_path << "\n";
    }

}  // namespace splitter
