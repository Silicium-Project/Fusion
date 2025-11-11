#include "splitter/partitioner.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <unordered_map>

#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

namespace splitter {

    using CallRef = std::pair<std::optional<uint64_t>, std::string>;
    using CallMatrix = std::vector<std::vector<CallRef>>;

    static bool should_skip_function(const Function& func) {
        if (func.name.empty())
            return true;
        if (func.name.front() == '_')
            return true;

        return func.name.find("@plt") != std::string::npos;
    }

    static BinaryPartition init_partition(Function& func,
                                          const std::string& binary_path,
                                          int partition_id) {
        analyze_function_loops(func);
        auto loop_info = detect_loop_patterns(func);
        BinaryPartition partition;

        partition.id = "func_" + std::to_string(partition_id) + "_" + func.name;
        partition.functions.push_back(func);
        partition.start_addr = func.start_addr;
        partition.end_addr = func.end_addr;
        partition.asm_code = function_to_asm(func);
        partition.raw_bytes = extract_binary_segment(binary_path, func.start_addr, func.end_addr);
        partition.is_parallelizable = loop_info["parallelizable"] == "true";

        return partition;
    }

    static std::vector<CallRef> collect_function_calls(const Function& func, BinaryPartition& partition) {
        std::set<std::string> reads;
        std::set<std::string> writes;
        std::vector<CallRef> calls;

        for (const auto& inst : func.instructions) {
            reads.insert(inst.reads.begin(), inst.reads.end());
            writes.insert(inst.writes.begin(), inst.writes.end());
            if (inst.is_call)
                calls.push_back({inst.target_addr, inst.operands});
        }

        std::set<std::string> inputs;
        std::set_difference(reads.begin(), reads.end(),
                            writes.begin(), writes.end(),
                            std::inserter(inputs, inputs.begin()));

        partition.inputs = inputs;
        partition.outputs = writes;

        return calls;
    }

    static std::unordered_map<uint64_t, size_t> build_address_index(const std::vector<BinaryPartition>& partitions) {
        std::unordered_map<uint64_t, size_t> index;

        for (size_t idx = 0; idx < partitions.size(); ++idx)
            for (const auto& func : partitions[idx].functions)
                index[func.start_addr] = idx;

        return index;
    }

    static std::unordered_map<std::string, size_t> build_id_index(const std::vector<BinaryPartition>& partitions) {
        std::unordered_map<std::string, size_t> index;

        for (size_t idx = 0; idx < partitions.size(); ++idx)
            index[partitions[idx].id] = idx;

        return index;
    }

    static std::string unresolved_label(const CallRef& call) {
        if (!call.second.empty())
            return call.second;
        if (!call.first.has_value())
            return "[indirect call]";

        std::ostringstream oss;

        oss << "0x" << std::hex << call.first.value();
        return oss.str();
    }

    static void resolve_dependencies(std::vector<BinaryPartition>& partitions,
                                     const CallMatrix& calls,
                                     const std::unordered_map<uint64_t, size_t>& addr_index,
                                     std::vector<std::set<std::string>>& parent_sets) {
        for (size_t idx = 0; idx < partitions.size(); ++idx) {
            std::set<std::string> dependency_set;
            std::set<std::string> unresolved_set;
            for (const auto& call : calls[idx]) {
                if (call.first.has_value()) {
                    uint64_t target = call.first.value();
                    auto it = addr_index.find(target);
                    if (it != addr_index.end()) {
                        const std::string& child_id = partitions[it->second].id;
                        if (child_id != partitions[idx].id) {
                            dependency_set.insert(child_id);
                            parent_sets[it->second].insert(partitions[idx].id);
                        }
                    } else {
                        unresolved_set.insert(unresolved_label(call));
                    }
                } else {
                    unresolved_set.insert(unresolved_label(call));
                }
            }
            partitions[idx].dependencies.assign(dependency_set.begin(), dependency_set.end());
            partitions[idx].unresolved_dependencies.assign(unresolved_set.begin(), unresolved_set.end());
        }
    }

    static void attach_parents(std::vector<BinaryPartition>& partitions,
                               const std::vector<std::set<std::string>>& parent_sets) {
        for (size_t idx = 0; idx < partitions.size(); ++idx)
            partitions[idx].parents.assign(parent_sets[idx].begin(), parent_sets[idx].end());
    }

    static void compute_external_inputs(std::vector<BinaryPartition>& partitions,
                                        const std::unordered_map<std::string, size_t>& id_index) {
        for (auto& partition : partitions) {
            std::set<std::string> provided;

            for (const auto& parent_id : partition.parents) {
                auto it = id_index.find(parent_id);

                if (it == id_index.end())
                    continue;

                const auto& outputs = partitions[it->second].outputs;
                provided.insert(outputs.begin(), outputs.end());
            }

            std::set<std::string> external;
            std::set_difference(partition.inputs.begin(), partition.inputs.end(),
                                provided.begin(), provided.end(),
                                std::inserter(external, external.begin()));
            partition.external_inputs = external;
        }
    }

    std::vector<uint8_t> extract_binary_segment(const std::string& binary_path,
                                        uint64_t start_addr, uint64_t end_addr) {

        std::vector<uint8_t> result;

        try {
            std::string cmd = "readelf -S " + binary_path;
            std::string output = exec_command(cmd);
            std::regex section_pattern("\\[\\s*\\d+\\]\\s+(\\.\\w+)\\s+\\w+\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
            std::smatch match;

            uint64_t text_offset = 0;
            uint64_t text_vaddr = 0;

            std::istringstream stream(output);
            std::string line;

            while (std::getline(stream, line))
                if (std::regex_search(line, match, section_pattern)
                && match[1].str().find(".text") != std::string::npos) {
                    text_vaddr = std::stoull(match[2].str(), nullptr, 16);
                    text_offset = std::stoull(match[3].str(), nullptr, 16);
                    break;
                }

            std::ifstream file(binary_path, std::ios::binary);

            if (!file)
                return result;

            uint64_t file_start = text_offset + (start_addr - text_vaddr);
            uint64_t file_end = text_offset + (end_addr - text_vaddr);

            file.seekg(file_start);
            const size_t segment_size = static_cast<size_t>(file_end - file_start);
            std::vector<char> buffer(segment_size);
            file.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
            result.assign(buffer.begin(), buffer.end());
        } catch (const std::exception& e) {
            std::cerr << "Avertissement: impossible d'extraire segment: " << e.what() << "\n";
        }
        return result;
    }

    std::string function_to_asm(const Function& func) {
        std::ostringstream oss;

        oss << "; Function: " << func.name << "\n";
        oss << "; Address: 0x" << std::hex << func.start_addr << " - 0x" << func.end_addr << "\n\n";

        for (const auto& inst : func.instructions)
            oss << "0x" << std::hex << inst.address << ": "
                << std::left << std::setw(8) << inst.opcode << " " << inst.operands << "\n";
        return oss.str();
    }

    std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions,
                                                const std::string& binary_path) {
        std::vector<BinaryPartition> partitions;
        CallMatrix call_refs;
        int partition_id = 0;

        for (auto& func : functions) {
            if (should_skip_function(func))
                continue;

            auto partition = init_partition(func, binary_path, partition_id);
            auto calls = collect_function_calls(func, partition);

            partitions.push_back(std::move(partition));
            call_refs.push_back(std::move(calls));
            ++partition_id;
        }

        auto addr_index = build_address_index(partitions);
        auto id_index = build_id_index(partitions);
        std::vector<std::set<std::string>> parent_sets(partitions.size());

        resolve_dependencies(partitions, call_refs, addr_index, parent_sets);
        attach_parents(partitions, parent_sets);
        compute_external_inputs(partitions, id_index);

        return partitions;
    }

}  // namespace splitter
