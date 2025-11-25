#include "splitter/artifacts.hpp"

#include <filesystem>
#include <functional>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <cstdlib>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <unordered_map>

#include "splitter/util.hpp"
#include "splitter/hash.hpp"

namespace splitter {

    namespace fs = std::filesystem;

    namespace {

        std::string env_wrapper() {
            const char* wrapper = std::getenv("SILICIUM_LIB_DETECT_WRAPPER");
            return (wrapper && *wrapper) ? std::string(wrapper) : std::string();
        }

        std::string wrap_command(const std::string& command) {
            std::string wrapper = env_wrapper();
            if (wrapper.empty())
                return command;
            return wrapper + " " + command;
        }

        size_t count_parallelizable(const std::vector<BinaryPartition>& partitions) {
            size_t count = 0;

            for (const auto& partition : partitions)
                if (partition.is_parallelizable)
                    ++count;
            return count;
        }

        std::string shell_quote(const std::string& path) {
            std::string quoted = "'";
            for (char ch : path) {
                if (ch == '\'')
                    quoted += "'\\''";
                else
                    quoted.push_back(ch);
            }
            quoted += "'";
            return quoted;
        }

        std::vector<std::string> detect_needed_via_readelf(const std::string& binary_path) {
            std::set<std::string> unique;
            const std::string command = wrap_command("readelf -d " + shell_quote(binary_path) + " 2>/dev/null");

            try {
                const std::string output = exec_command(command);
                std::regex needed_regex(R"(\(NEEDED\).*\[(.+?)\])");
                std::smatch match;
                std::istringstream stream(output);
                std::string line;
                while (std::getline(stream, line))
                    if (std::regex_search(line, match, needed_regex) && match.size() > 1)
                        unique.insert(match[1].str());
            } catch (const std::exception&) {
                return {};
            }

            return std::vector<std::string>(unique.begin(), unique.end());
        }

        std::vector<LibraryEntry> detect_libraries_with_ldd(const std::string& binary_path) {
            std::vector<LibraryEntry> libraries;
            const std::string command = wrap_command("ldd " + shell_quote(binary_path) + " 2>/dev/null");

            try {
                const std::string output = exec_command(command);
                std::istringstream stream(output);
                std::string line;
                std::regex mapping_regex(R"(^\s*([^\s]+)\s+=>\s+([^\s]+))");
                std::regex direct_regex(R"(^\s*([^\s]+)\s+\((0x[0-9a-fA-F]+)\))");
                std::smatch match;

                while (std::getline(stream, line)) {
                    if (std::regex_search(line, match, mapping_regex) && match.size() > 2) {
                        const std::string name = match[1].str();
                        const std::string path = match[2].str();
                        if (path == "not" || path == "found")
                            continue;
                        if (!path.empty() && path[0] == '/')
                            libraries.push_back({name, path, name, {}});
                    } else if (std::regex_search(line, match, direct_regex) && match.size() > 1) {
                        // Entries such as linux-vdso; no filesystem path to load.
                        continue;
                    }
                }
            } catch (const std::exception&) {
                return {};
            }

            return libraries;
        }

        std::set<std::string> list_exported_symbols(const std::string& path) {
            if (path.empty())
                return {};

            std::set<std::string> symbols;
            const std::string command =
                wrap_command("nm -D --defined-only " + shell_quote(path) + " 2>/dev/null");

            try {
                const std::string output = exec_command(command);
                std::istringstream stream(output);
                std::string line;

                while (std::getline(stream, line)) {
                    std::istringstream parser(trim(line));
                    std::string address, type, name;
                    if (!(parser >> address >> type >> name))
                        continue;
                    if (!name.empty()) {
                        auto at = name.find('@');
                        if (at != std::string::npos)
                            name = name.substr(0, at);
                        symbols.insert(name);
                    }
                }
            } catch (const std::exception&) {
                return {};
            }

            return symbols;
        }

        std::vector<LibraryEntry> detect_required_libraries(const std::string& binary_path) {
            auto libraries = detect_libraries_with_ldd(binary_path);
            if (!libraries.empty())
                return libraries;

            auto names = detect_needed_via_readelf(binary_path);
            libraries.reserve(names.size());
            for (const auto& name : names)
                libraries.push_back({name, "", name, {}});
            return libraries;
        }

        std::unordered_map<std::string, std::string> build_symbol_index(
                const std::vector<LibraryEntry>& libraries) {
        std::unordered_map<std::string, std::string> index;
        for (const auto& entry : libraries) {
            if (entry.path.empty())
                continue;
            auto symbols = list_exported_symbols(entry.path);
            for (const auto& symbol : symbols)
                index.emplace(symbol, entry.name);
        }
        return index;
    }

        template <typename Container>
        void hash_strings(FnvHasher& h, const Container& c) {
            for (const auto& s : c)
                h.add_string(s);
            h.add_byte(0x7f);
        }

        std::string compute_partition_hash(const BinaryPartition& p,
                                           const std::set<std::string>& resolved_libs) {
            FnvHasher h;
            h.add_string(p.id);
            h.add_uint64(p.start_addr);
            h.add_uint64(p.end_addr);
            h.add_string(p.bin_hash);
            h.add_uint64(p.raw_bytes.size());
            h.add_bool(p.is_parallelizable);
            h.add_bool(p.requires_display);
            hash_strings(h, p.inputs);
            hash_strings(h, p.external_inputs);
            hash_strings(h, p.outputs);
            hash_strings(h, p.external_calls);
            hash_strings(h, resolved_libs);
            hash_strings(h, p.parents);
            hash_strings(h, p.dependencies);
            hash_strings(h, p.unresolved_dependencies);
            return h.hex();
        }

        std::string compute_memory_hash(const std::vector<MemorySegment>& segments) {
            FnvHasher h;
            for (const auto& seg : segments) {
                h.add_string(seg.name);
                h.add_uint64(seg.address);
                h.add_string(hash_bytes(seg.bytes));
            }
            return h.hex();
        }

        std::string compute_summary_hash(const std::string& binary_hash,
                                         const std::string& memory_hash,
                                         bool can_split,
                                         const std::vector<std::string>& required_libraries,
                                         const std::vector<LibraryEntry>& libraries,
                                         const std::vector<std::pair<std::string, std::string>>& partition_hashes) {
            FnvHasher h;
            h.add_string(binary_hash);
            h.add_string(memory_hash);
            h.add_bool(can_split);

            auto libs_sorted = required_libraries;
            std::sort(libs_sorted.begin(), libs_sorted.end());
            hash_strings(h, libs_sorted);

            std::vector<LibraryEntry> libs = libraries;
            std::sort(libs.begin(), libs.end(), [](const auto& a, const auto& b) { return a.name < b.name; });
            for (const auto& lib : libs) {
                h.add_string(lib.name);
                h.add_string(lib.path);
                h.add_string(lib.soname.empty() ? lib.name : lib.soname);
                h.add_string(lib.build_id);
            }

            std::vector<std::pair<std::string, std::string>> parts = partition_hashes;
            std::sort(parts.begin(), parts.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
            for (const auto& ph : parts) {
                h.add_string(ph.first);   // id
                h.add_string(ph.second);  // hash
            }

            return h.hex();
        }

        std::set<std::string> resolve_partition_libraries(
                const BinaryPartition& partition,
                const std::unordered_map<std::string, std::string>& symbol_index) {
            std::set<std::string> names;
            for (const auto& symbol : partition.external_calls) {
                auto it = symbol_index.find(symbol);
                if (it != symbol_index.end())
                    names.insert(it->second);
            }
            return names;
        }

        std::string hex_string(uint64_t value) {
            std::ostringstream oss;
            oss << "0x" << std::hex << value;

            return oss.str();
        }

        std::optional<std::reference_wrapper<const PartitionFiles>> artifact_for(
                size_t idx, const std::vector<PartitionFiles>& artifacts) {

            if (idx >= artifacts.size())
                return std::nullopt;
            return std::cref(artifacts[idx]);
        }

        void write_partition_entry(std::ofstream& out,
                const BinaryPartition& partition,
                const std::optional<std::reference_wrapper<const PartitionFiles>>& files,
                const std::unordered_map<std::string, std::string>& symbol_index,
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
            out << "      \"external_calls\": "
                << set_to_json(partition.external_calls) << ",\n";
            out << "      \"requires_display\": "
                << (partition.requires_display ? "true" : "false") << ",\n";
            out << "      \"bin_hash\": \"" << json_escape(partition.bin_hash) << "\",\n";
            out << "      \"outputs\": " << set_to_json(partition.outputs) << ",\n";
            out << "      \"parents\": " << vector_to_json(partition.parents) << ",\n";
            out << "      \"dependencies\": " << vector_to_json(partition.dependencies) << ",\n";
            out << "      \"unresolved_calls\": "
                << vector_to_json(partition.unresolved_dependencies) << ",\n";
            out << "      \"required_libraries\": "
                << set_to_json(resolve_partition_libraries(partition, symbol_index)) << ",\n";
            out << "      \"partition_hash\": \"" << json_escape(partition.partition_hash) << "\",\n";

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

    }  // namespace

    ArtifactBuilder::ArtifactBuilder(std::string output_dir)
    : output_dir_(std::move(output_dir)) {
        fs::create_directories(output_dir_);
    }

    PartitionFiles ArtifactBuilder::create_partition(const BinaryPartition& partition) const {
        fs::create_directories(output_dir_);

        PartitionFiles files;
        files.asm_file = output_dir_ + "/" + partition.id + ".asm";
        files.bin_file = output_dir_ + "/" + partition.id + ".bin";
        files.wrapper_file = output_dir_ + "/" + partition.id + "_wrapper.c";

        write_text_file(files.asm_file, partition.asm_code);
        write_binary_file(files.bin_file, partition.raw_bytes);
        write_wrapper(files.wrapper_file, partition.id);

        return files;
    }

    void ArtifactBuilder::write_summary(const std::vector<BinaryPartition>& partitions,
                                        const std::vector<PartitionFiles>& artifacts,
                                        const std::vector<MemorySegment>& memory_segments,
                                        const std::string& binary_path) const {
        fs::create_directories(output_dir_);

        std::string summary_path = output_dir_ + "/summary.json";
        std::ofstream summary;

        if (!open_summary_file(summary_path, summary))
            return;

        auto libraries = detect_required_libraries(binary_path);
        std::vector<std::string> library_names;
        {
            std::set<std::string> unique;
            for (const auto& entry : libraries)
                unique.insert(entry.name);
            library_names.assign(unique.begin(), unique.end());
        }
        auto symbol_index = build_symbol_index(libraries);
        const std::string binary_hash = hash_file(binary_path);
        bool can_split = true;
        if (const char* env = std::getenv("SPLITTER_CAN_SPLIT"))
            can_split = std::string(env) != "0" && std::string(env) != "false";

        // Hash mémoire initiale
        std::string memory_hash = compute_memory_hash(memory_segments);

        std::vector<std::pair<std::string, std::string>> partition_hashes;
        partition_hashes.reserve(partitions.size());
        for (auto& p : const_cast<std::vector<BinaryPartition>&>(partitions)) {
            auto resolved_libs = resolve_partition_libraries(p, symbol_index);
            p.partition_hash = compute_partition_hash(p, resolved_libs);
            partition_hashes.emplace_back(p.id, p.partition_hash);
        }
        const std::string summary_hash = compute_summary_hash(binary_hash, memory_hash, can_split,
                                                              library_names, libraries, partition_hashes);

        write_summary_header(summary, binary_path, partitions.size(),
                             count_parallelizable(partitions), library_names, libraries,
                             binary_hash, can_split, memory_hash, summary_hash);
        write_partitions_block(summary, partitions, artifacts, symbol_index);
        summary << "  ],\n";
        write_memory_block(summary, memory_segments);
        write_summary_footer(summary);

        std::cout << "\nRésumé: " << summary_path << "\n";
    }

    void ArtifactBuilder::write_text_file(const std::string& path, const std::string& content) const {
        std::ofstream file(path);
        file << content;
    }

    void ArtifactBuilder::write_binary_file(const std::string& path, const std::vector<uint8_t>& data) const {
        std::ofstream file(path, std::ios::binary);
        std::vector<char> buffer(data.begin(), data.end());
        file.write(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    }

    void ArtifactBuilder::write_wrapper(const std::string& path, const std::string& partition_id) const {
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

    bool ArtifactBuilder::open_summary_file(const std::string& path, std::ofstream& out) const {
        out.open(path);
        if (out)
            return true;
        std::cerr << "Avertissement: impossible d'écrire " << path << "\n";
        return false;
    }

    void ArtifactBuilder::write_summary_header(std::ofstream& out,
                                               const std::string& binary_path,
                                               size_t partition_count,
                                               size_t parallelizable_count,
                                               const std::vector<std::string>& required_libraries,
                                               const std::vector<LibraryEntry>& libraries,
                                               const std::string& binary_hash,
                                               bool can_split,
                                               const std::string& memory_hash,
                                               const std::string& summary_hash) const {
        out << "{\n";
        out << "  \"binary\": \"" << json_escape(binary_path) << "\",\n";
        out << "  \"binary_hash\": \"" << json_escape(binary_hash) << "\",\n";
        out << "  \"can_split\": " << (can_split ? "true" : "false") << ",\n";
        out << "  \"memory_hash\": \"" << json_escape(memory_hash) << "\",\n";
        out << "  \"summary_hash\": \"" << json_escape(summary_hash) << "\",\n";
        out << "  \"partitions_count\": " << partition_count << ",\n";
        out << "  \"parallelizable_count\": " << parallelizable_count << ",\n";
        out << "  \"required_libraries\": " << vector_to_json(required_libraries) << ",\n";
        out << "  \"libraries\": [\n";
        for (size_t i = 0; i < libraries.size(); ++i) {
            const auto& lib = libraries[i];
            const bool is_last = (i + 1 == libraries.size());
            out << "    {\n";
            out << "      \"name\": \"" << json_escape(lib.name) << "\",\n";
            out << "      \"path\": \"" << json_escape(lib.path) << "\",\n";
            out << "      \"soname\": \"" << json_escape(lib.soname.empty() ? lib.name : lib.soname) << "\",\n";
            out << "      \"build_id\": \"" << json_escape(lib.build_id) << "\"\n";
            out << "    }" << (is_last ? "" : ",") << "\n";
        }
        out << "  ],\n";
        out << "  \"partitions\": [\n";
    }

    void ArtifactBuilder::write_summary_footer(std::ofstream& out) const {
        out << "}\n";
    }

    void ArtifactBuilder::write_partitions_block(std::ofstream& out,
                                                 const std::vector<BinaryPartition>& partitions,
                                                 const std::vector<PartitionFiles>& artifacts,
                                                 const std::unordered_map<std::string, std::string>& symbol_index) const {
        for (size_t idx = 0; idx < partitions.size(); ++idx) {
            const bool is_last = (idx + 1 == partitions.size());
            write_partition_entry(out, partitions[idx], artifact_for(idx, artifacts), symbol_index, is_last);
        }
    }

    static std::string bytes_to_hex(const std::vector<uint8_t>& bytes) {
        std::ostringstream oss;
        oss << std::hex << std::setfill('0');
        for (uint8_t byte : bytes)
            oss << std::setw(2) << static_cast<int>(byte);
        return oss.str();
    }

    void ArtifactBuilder::write_memory_block(std::ofstream& out,
                                             const std::vector<MemorySegment>& memory_segments) const {
        out << "  \"initial_memory\": [\n";
        for (size_t idx = 0; idx < memory_segments.size(); ++idx) {
            const auto& segment = memory_segments[idx];
            bool is_last = (idx + 1 == memory_segments.size());
            out << "    {\n";
            out << "      \"name\": \"" << json_escape(segment.name) << "\",\n";
            out << "      \"address\": \"0x" << std::hex << segment.address << "\",\n";
            out << std::dec;
            out << "      \"bytes\": \"" << bytes_to_hex(segment.bytes) << "\"\n";
            out << "    }" << (is_last ? "\n" : ",\n");
        }
        out << "  ]\n";
    }

    PartitionFiles create_standalone_partition(const BinaryPartition& partition,
                                               const std::string& output_dir) {
        ArtifactBuilder builder(output_dir);
        return builder.create_partition(partition);
    }

    void write_summary(const std::vector<BinaryPartition>& partitions,
                       const std::vector<PartitionFiles>& artifacts,
                       const std::vector<MemorySegment>& memory_segments,
                       const std::string& output_dir,
                       const std::string& binary_path) {
        ArtifactBuilder builder(output_dir);
        builder.write_summary(partitions, artifacts, memory_segments, binary_path);
    }

}  // namespace splitter
