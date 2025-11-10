#include "splitter/partitioner.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <regex>
#include <set>
#include <sstream>
#include <unordered_map>

#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

namespace splitter {

namespace fs = std::filesystem;

std::vector<uint8_t> extract_binary_segment(const std::string& binary_path,
                                            uint64_t start_addr,
                                            uint64_t end_addr) {
    std::vector<uint8_t> result;
    try {
        std::string cmd = "readelf -S " + binary_path;
        std::string output = exec_command(cmd);
        std::regex section_pattern(
            "\\[\\s*\\d+\\]\\s+(\\.\\w+)\\s+\\w+\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;
        uint64_t text_offset = 0;
        uint64_t text_vaddr = 0;
        std::istringstream stream(output);
        std::string line;
        while (std::getline(stream, line)) {
            if (std::regex_search(line, match, section_pattern) &&
                match[1].str().find(".text") != std::string::npos) {
                text_vaddr = std::stoull(match[2].str(), nullptr, 16);
                text_offset = std::stoull(match[3].str(), nullptr, 16);
                break;
            }
        }
        std::ifstream file(binary_path, std::ios::binary);
        if (!file) return result;
        uint64_t file_start = text_offset + (start_addr - text_vaddr);
        uint64_t file_end = text_offset + (end_addr - text_vaddr);
        file.seekg(file_start);
        result.resize(file_end - file_start);
        file.read(reinterpret_cast<char*>(result.data()), result.size());
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire segment: " << e.what() << "\n";
    }
    return result;
}

std::string function_to_asm(const Function& func) {
    std::ostringstream oss;
    oss << "; Function: " << func.name << "\n";
    oss << "; Address: 0x" << std::hex << func.start_addr << " - 0x" << func.end_addr
        << "\n\n";
    for (const auto& inst : func.instructions) {
        oss << "0x" << std::hex << inst.address << ": "
            << std::left << std::setw(8) << inst.opcode << " " << inst.operands << "\n";
    }
    return oss.str();
}

std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions,
                                              const std::string& binary_path) {
    std::vector<BinaryPartition> partitions;
    std::vector<std::vector<std::pair<std::optional<uint64_t>, std::string>>> call_refs;
    int partition_id = 0;

    for (auto& func : functions) {
        if (func.name.empty() || func.name[0] == '_' || func.name.find("@plt") != std::string::npos) {
            continue;
        }
        analyze_function_loops(func);
        auto loop_info = detect_loop_patterns(func);
        BinaryPartition partition;
        partition.id = "func_" + std::to_string(partition_id) + "_" + func.name;
        partition.functions.push_back(func);
        partition.start_addr = func.start_addr;
        partition.end_addr = func.end_addr;
        partition.asm_code = function_to_asm(func);
        partition.raw_bytes = extract_binary_segment(binary_path, func.start_addr, func.end_addr);
        partition.is_parallelizable = (loop_info["parallelizable"] == "true");

        std::set<std::string> all_reads, all_writes;
        std::vector<std::pair<std::optional<uint64_t>, std::string>> function_calls;
        for (const auto& inst : func.instructions) {
            all_reads.insert(inst.reads.begin(), inst.reads.end());
            all_writes.insert(inst.writes.begin(), inst.writes.end());
            if (inst.is_call) {
                function_calls.push_back({inst.target_addr, inst.operands});
            }
        }
        std::set_difference(all_reads.begin(), all_reads.end(),
                            all_writes.begin(), all_writes.end(),
                            std::inserter(partition.inputs, partition.inputs.begin()));
        partition.outputs = all_writes;
        partitions.push_back(partition);
        call_refs.push_back(function_calls);
        ++partition_id;
    }

    std::unordered_map<uint64_t, size_t> addr_to_partition;
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        for (const auto& func : partitions[idx].functions) {
            addr_to_partition[func.start_addr] = idx;
        }
    }
    std::unordered_map<std::string, size_t> id_to_index;
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        id_to_index[partitions[idx].id] = idx;
    }

    std::vector<std::set<std::string>> parent_sets(partitions.size());
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> dependency_set;
        std::set<std::string> unresolved_set;
        for (const auto& call_info : call_refs[idx]) {
            if (call_info.first.has_value()) {
                uint64_t target = call_info.first.value();
                auto it = addr_to_partition.find(target);
                if (it != addr_to_partition.end()) {
                    const std::string& child_id = partitions[it->second].id;
                    if (child_id != partitions[idx].id) {
                        dependency_set.insert(child_id);
                        parent_sets[it->second].insert(partitions[idx].id);
                    }
                } else {
                    std::ostringstream oss;
                    if (!call_info.second.empty()) {
                        oss << call_info.second;
                    } else {
                        oss << "0x" << std::hex << target;
                    }
                    unresolved_set.insert(oss.str());
                }
            } else {
                if (!call_info.second.empty()) {
                    unresolved_set.insert(call_info.second);
                } else {
                    unresolved_set.insert("[indirect call]");
                }
            }
        }
        partitions[idx].dependencies.assign(dependency_set.begin(), dependency_set.end());
        partitions[idx].unresolved_dependencies.assign(unresolved_set.begin(), unresolved_set.end());
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        partitions[idx].parents.assign(parent_sets[idx].begin(), parent_sets[idx].end());
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> provided;
        for (const auto& parent_id : partitions[idx].parents) {
            auto it = id_to_index.find(parent_id);
            if (it != id_to_index.end()) {
                const auto& parent_outputs = partitions[it->second].outputs;
                provided.insert(parent_outputs.begin(), parent_outputs.end());
            }
        }
        std::set<std::string> external_inputs;
        std::set_difference(partitions[idx].inputs.begin(), partitions[idx].inputs.end(),
                            provided.begin(), provided.end(),
                            std::inserter(external_inputs, external_inputs.begin()));
        partitions[idx].external_inputs = external_inputs;
    }

    return partitions;
}

}  // namespace splitter
