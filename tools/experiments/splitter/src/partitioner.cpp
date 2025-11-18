#include "splitter/partitioner.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <unordered_map>
#include <utility>

#include "splitter/instruction_analysis.hpp"
#include "splitter/util.hpp"

namespace splitter {

    namespace {

        using CallRef = std::pair<std::optional<uint64_t>, std::string>;
        using CallMatrix = std::vector<std::vector<CallRef>>;

        bool should_skip_function(const Function& func) {
            if (func.name.empty())
                return true;
            if (func.name.front() == '_')
                return true;

            return func.name.find("@plt") != std::string::npos;
        }

        std::string unresolved_label(const CallRef& call) {
            if (!call.second.empty())
                return call.second;
            if (!call.first.has_value())
                return "[indirect call]";

            std::ostringstream oss;

            oss << "0x" << std::hex << call.first.value();
            return oss.str();
        }
 
        std::string normalize_external_symbol(const CallRef& call) {
            std::string operand = splitter::trim(call.second);
            if (!operand.empty()) {
                auto comment_pos = operand.find('#');
                if (comment_pos != std::string::npos)
                    operand = splitter::trim(operand.substr(comment_pos + 1));
            }

            std::string candidate;
            const size_t lt = operand.find('<');
            size_t gt = std::string::npos;
            if (lt != std::string::npos)
                gt = operand.find('>', lt + 1);
            if (lt != std::string::npos && gt != std::string::npos && gt > lt + 1)
                candidate = operand.substr(lt + 1, gt - lt - 1);
            else
                candidate = operand;

            const auto plus_pos = candidate.find('+');
            if (plus_pos != std::string::npos)
                candidate = candidate.substr(0, plus_pos);

            const auto at_pos = candidate.find('@');
            if (at_pos != std::string::npos)
                candidate = candidate.substr(0, at_pos);

            candidate = splitter::trim(candidate);

            auto is_allowed = [](char ch) {
                unsigned char uch = static_cast<unsigned char>(ch);
                return std::isalnum(uch) || ch == '_' || ch == '.' || ch == '-';
            };

            size_t start = 0;
            while (start < candidate.size() && !is_allowed(candidate[start]))
                ++start;
            size_t end = candidate.size();
            while (end > start && !is_allowed(candidate[end - 1]))
                --end;

            if (start >= end)
                candidate.clear();
            else
                candidate = candidate.substr(start, end - start);

            if (!candidate.empty())
                return candidate;

            if (call.first.has_value()) {
                std::ostringstream oss;
                oss << "0x" << std::hex << call.first.value();
                return oss.str();
            }

            return {};
        }

    }  // namespace

    class Partitioner::Impl {
    public:
        explicit Impl(std::string binary_path)
        : binary_path_(std::move(binary_path)) {}

        std::vector<BinaryPartition> run(std::vector<Function>& functions) {
            reset();

            int partition_id = 0;
            for (auto& func : functions) {
                if (should_skip_function(func))
                    continue;

                auto partition = init_partition(func, partition_id);
                auto calls = collect_function_calls(func, partition);

                partitions_.push_back(std::move(partition));
                call_refs_.push_back(std::move(calls));
                ++partition_id;
            }

            if (partitions_.empty()) {
                reset();
                return {};
            }

            build_indices();
            resolve_dependencies();
            attach_parents();
            collect_external_calls();
            compute_external_inputs();

            auto output = std::move(partitions_);
            reset();

            return output;
        }

    private:
        BinaryPartition init_partition(Function& func, int partition_id) const {
            analyze_function_loops(func);
            auto loop_info = detect_loop_patterns(func);
            BinaryPartition partition;

            partition.id = "func_" + std::to_string(partition_id) + "_" + func.name;
            partition.functions.push_back(func);
            partition.start_addr = func.start_addr;
            partition.end_addr = func.end_addr;
            partition.asm_code = function_to_asm(func);
            partition.raw_bytes = extract_binary_segment(binary_path_, func.start_addr, func.end_addr);
            partition.is_parallelizable = loop_info.parallelizable;

            return partition;
        }

        std::vector<CallRef> collect_function_calls(const Function& func, BinaryPartition& partition) const {
            std::set<std::string> outputs;
            std::set<std::string> observed_inputs;
            std::set<std::string> written_registers;
            std::vector<CallRef> calls;

            for (const auto& inst : func.instructions) {
                for (const auto& reg : inst.reads)
                    if (!written_registers.count(reg))
                        observed_inputs.insert(reg);

                for (const auto& reg : inst.writes) {
                    outputs.insert(reg);
                    written_registers.insert(reg);
                }

                const bool external_jump = inst.is_jump && inst.target_addr.has_value()
                                           && (inst.target_addr.value() < func.start_addr
                                               || inst.target_addr.value() >= func.end_addr);
                if (inst.is_call || external_jump)
                    calls.push_back({inst.target_addr, inst.operands});
            }

            partition.inputs = observed_inputs;
            partition.outputs = outputs;

            return calls;
        }

        void build_indices() {
            addr_index_.clear();
            id_index_.clear();
            parent_sets_.clear();

            parent_sets_.resize(partitions_.size());

            for (size_t idx = 0; idx < partitions_.size(); ++idx) {
                for (const auto& func : partitions_[idx].functions)
                    addr_index_[func.start_addr] = idx;

                id_index_[partitions_[idx].id] = idx;
            }
        }

        void resolve_dependencies() {
            for (size_t idx = 0; idx < partitions_.size(); ++idx) {
                std::set<std::string> dependency_set;
                std::set<std::string> unresolved_set;

                for (const auto& call : call_refs_[idx]) {
                    if (call.first.has_value()) {
                        uint64_t target = call.first.value();
                        auto it = addr_index_.find(target);

                        if (it != addr_index_.end()) {
                            const std::string& child_id = partitions_[it->second].id;

                            if (child_id != partitions_[idx].id) {
                                dependency_set.insert(child_id);
                                parent_sets_[it->second].insert(partitions_[idx].id);
                            }
                        } else
                            unresolved_set.insert(unresolved_label(call));
                    } else
                        unresolved_set.insert(unresolved_label(call));
                }

                partitions_[idx].dependencies.assign(dependency_set.begin(), dependency_set.end());
                partitions_[idx].unresolved_dependencies.assign(unresolved_set.begin(), unresolved_set.end());
            }
        }

        void attach_parents() {
            for (size_t idx = 0; idx < partitions_.size(); ++idx)
                partitions_[idx].parents.assign(parent_sets_[idx].begin(), parent_sets_[idx].end());
        }

        bool resolves_to_partition(size_t idx, const CallRef& call) const {
            if (!call.first.has_value())
                return false;
            auto it = addr_index_.find(call.first.value());
            if (it == addr_index_.end())
                return false;
            const auto& child_id = partitions_[it->second].id;
            return child_id != partitions_[idx].id;
        }

        void collect_external_calls() {
            for (size_t idx = 0; idx < partitions_.size(); ++idx) {
                std::set<std::string> names;
                for (const auto& call : call_refs_[idx]) {
                    if (resolves_to_partition(idx, call))
                        continue;
                    auto symbol = normalize_external_symbol(call);
                    if (!symbol.empty())
                        names.insert(symbol);
                }
                partitions_[idx].external_calls = std::move(names);
            }
        }

        void compute_external_inputs() {
            for (auto& partition : partitions_) {
                std::set<std::string> provided;

                for (const auto& parent_id : partition.parents) {
                    auto it = id_index_.find(parent_id);

                    if (it == id_index_.end())
                        continue;

                    const auto& outputs = partitions_[it->second].outputs;
                    provided.insert(outputs.begin(), outputs.end());
                }

                std::set<std::string> external;
                std::set_difference(partition.inputs.begin(), partition.inputs.end(),
                                    provided.begin(), provided.end(),
                                    std::inserter(external, external.begin()));

                partition.external_inputs = external;
            }
        }

        void reset() {
            partitions_.clear();
            call_refs_.clear();
            addr_index_.clear();
            id_index_.clear();
            parent_sets_.clear();
        }

        std::string binary_path_;
        std::vector<BinaryPartition> partitions_;
        CallMatrix call_refs_;
        std::unordered_map<uint64_t, size_t> addr_index_;
        std::unordered_map<std::string, size_t> id_index_;
        std::vector<std::set<std::string>> parent_sets_;
    };

    Partitioner::Partitioner(std::string binary_path)
    : impl_(std::make_unique<Impl>(std::move(binary_path))) {}

    Partitioner::~Partitioner() = default;
    Partitioner::Partitioner(Partitioner&&) noexcept = default;
    Partitioner& Partitioner::operator=(Partitioner&&) noexcept = default;

    std::vector<BinaryPartition> Partitioner::run(std::vector<Function>& functions) {
        return impl_->run(functions);
    }

    std::vector<BinaryPartition> partition_binary(std::vector<Function>& functions,
                                                  const std::string& binary_path) {
        Partitioner partitioner(binary_path);
        return partitioner.run(functions);
    }

std::vector<uint8_t> extract_binary_segment(const std::string& binary_path,
                                            uint64_t start_addr, uint64_t end_addr) {

    std::vector<uint8_t> result;

    try {
        std::string cmd = "readelf -W -S " + binary_path;
        std::string output = exec_command(cmd);
        std::regex section_pattern("\\[\\s*\\d+\\]\\s+([^\\s]+)\\s+([^\\s]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;

        uint64_t text_offset = 0;
        uint64_t text_vaddr = 0;

        std::istringstream stream(output);
        std::string line;

        while (std::getline(stream, line))
            if (std::regex_search(line, match, section_pattern)
            && match[1].str().find(".text") != std::string::npos) {
                text_vaddr = std::stoull(match[3].str(), nullptr, 16);
                text_offset = std::stoull(match[4].str(), nullptr, 16);

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

std::vector<MemorySegment> extract_data_sections(const std::string& binary_path) {

    std::vector<MemorySegment> segments;

    try {
        std::string cmd = "readelf -W -S " + binary_path;
        std::string output = exec_command(cmd);
        std::regex section_pattern("\\[\\s*\\d+\\]\\s+([^\\s]+)\\s+([^\\s]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)\\s+([0-9a-f]+)");
        std::smatch match;

        std::ifstream file(binary_path, std::ios::binary);
        std::istringstream stream(output);
        std::string line;

        while (std::getline(stream, line)) {
            if (!std::regex_search(line, match, section_pattern))
                continue;

            std::string name = match[1].str();
            std::string type = match[2].str();

            const bool is_data = name.find(".data") != std::string::npos;
            const bool is_bss = name.find(".bss") != std::string::npos;
            const bool is_got = name.find(".got") != std::string::npos;
            const bool is_plt = name.find(".plt") != std::string::npos;
            const bool is_rodata = name.find(".rodata") != std::string::npos;
            if (!is_data && !is_bss && !is_got && !is_plt && !is_rodata)
                continue;

            uint64_t addr = std::stoull(match[3].str(), nullptr, 16);
            uint64_t offset = std::stoull(match[4].str(), nullptr, 16);
            uint64_t size = std::stoull(match[5].str(), nullptr, 16);

            MemorySegment segment;
            segment.name = name;
            segment.address = addr;

            if (type == "NOBITS") {
                segment.bytes.resize(size, 0);
            } else if (size != 0) {
                segment.bytes.resize(size);
                if (file) {
                    file.seekg(static_cast<std::streamoff>(offset));
                    file.read(reinterpret_cast<char*>(segment.bytes.data()), static_cast<std::streamsize>(size));
                }
            }

            if (!segment.bytes.empty())
                segments.push_back(std::move(segment));
        }
    } catch (const std::exception& e) {
        std::cerr << "Avertissement: impossible d'extraire les sections de données: " << e.what() << "\n";
    }

    return segments;
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

}  // namespace splitter
