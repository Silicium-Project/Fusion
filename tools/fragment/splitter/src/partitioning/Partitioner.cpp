#include "splitter/partitioning/Partitioner.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <unordered_map>
#include <utility>

#include "splitter/partitioning/BinaryExtractor.hpp"
#include "splitter/support/HashUtil.hpp"
#include "splitter/support/StringUtil.hpp"

namespace splitter {

namespace {

using CallRef = std::pair<std::optional<uint64_t>, std::string>;
using CallMatrix = std::vector<std::vector<CallRef>>;

bool ShouldSkipFunction(const Function& func) {
    if (func.Name().empty())
        return true;
    if (func.Name().front() == '_')
        return true;
    return func.Name().find("@plt") != std::string::npos;
}

std::string UnresolvedLabel(const CallRef& call) {
    if (!call.second.empty())
        return call.second;
    if (!call.first.has_value())
        return "[indirect call]";

    std::ostringstream oss;
    oss << "0x" << std::hex << call.first.value();
    return oss.str();
}

std::string NormalizeExternalSymbol(const CallRef& call) {
    std::string operand = Trim(call.second);
    if (!operand.empty()) {
        auto comment_pos = operand.find('#');
        if (comment_pos != std::string::npos)
            operand = Trim(operand.substr(comment_pos + 1));
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

    candidate = Trim(candidate);

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

std::vector<std::string> GuiPrefixes() {
    static std::vector<std::string> cached;
    static bool initialized = false;

    if (!initialized) {
        initialized = true;
        if (const char* env = std::getenv("SPLITTER_GUI_PREFIXES")) {
            std::string raw(env);
            std::stringstream ss(raw);
            std::string item;
            while (std::getline(ss, item, ',')) {
                const auto start = item.find_first_not_of(" \t");
                const auto end = item.find_last_not_of(" \t");
                if (start != std::string::npos && end != std::string::npos && end >= start)
                    cached.emplace_back(item.substr(start, end - start + 1));
            }
        }
        if (cached.empty()) {
            cached = {
                "sfRenderWindow_", "sfRenderTexture_", "sfWindow_",
                "sfView_",        "sfSprite_",        "sfKeyboard_",
                "sfMouse_",       "glX",              "SDL_"
            };
        }
    }
    return cached;
}

bool IsGuiSymbol(const std::string& symbol) {
    const auto& prefixes = GuiPrefixes();
    for (const auto& prefix : prefixes)
        if (symbol.rfind(prefix, 0) == 0)
            return true;
    return false;
}

std::string FunctionToAsm(const Function& func) {
    std::ostringstream oss;
    oss << "; Function: " << func.Name() << "\n";
    oss << "; Address: 0x" << std::hex << func.StartAddr() << " - 0x" << func.EndAddr() << "\n\n";

    for (const auto& inst : func.Instructions())
        oss << "0x" << std::hex << inst.Address() << ": "
            << std::left << std::setw(8) << inst.Opcode() << " " << inst.Operands() << "\n";
    return oss.str();
}

}  // namespace

Partitioner::Partitioner(BinaryPath binary_path, const IInstructionAnalyzer& analyzer, const BinaryExtractor& extractor)
    : binary_path_(std::move(binary_path)), analyzer_(analyzer), extractor_(extractor) {}

std::vector<Partition> Partitioner::Run(std::vector<Function>& functions) {
    std::vector<Partition> partitions;
    CallMatrix call_refs;
    std::unordered_map<uint64_t, size_t> addr_index;
    std::unordered_map<std::string, size_t> id_index;
    std::vector<std::set<std::string>> parent_sets;

    int partition_id = 0;
    for (auto& func : functions) {
        if (ShouldSkipFunction(func))
            continue;

        analyzer_.AnalyzeFunctionLoops(func);
        auto loop_info = analyzer_.DetectLoopPatterns(func);

        Partition partition;
        partition.SetId("func_" + std::to_string(partition_id) + "_" + func.Name());
        partition.Functions().push_back(func);
        partition.SetStartAddr(func.StartAddr());
        partition.SetEndAddr(func.EndAddr());
        partition.SetAsmCode(FunctionToAsm(func));
        partition.RawBytes() = extractor_.ExtractSegment(binary_path_.Value(), func.StartAddr(), func.EndAddr());
        partition.SetIsParallelizable(loop_info.parallelizable);

        std::set<std::string> outputs;
        std::set<std::string> observed_inputs;
        std::set<std::string> written_registers;
        std::vector<CallRef> calls;

        for (const auto& inst : func.Instructions()) {
            for (const auto& reg : inst.Reads())
                if (!written_registers.count(reg))
                    observed_inputs.insert(reg);

            for (const auto& reg : inst.Writes()) {
                outputs.insert(reg);
                written_registers.insert(reg);
            }

            const bool external_jump = inst.IsJump() && inst.TargetAddr().has_value()
                                       && (inst.TargetAddr().value() < func.StartAddr()
                                           || inst.TargetAddr().value() >= func.EndAddr());
            if (inst.IsCall() || external_jump)
                calls.push_back({inst.TargetAddr(), inst.Operands()});
        }

        partition.Inputs() = observed_inputs;
        partition.Outputs() = outputs;

        partitions.push_back(std::move(partition));
        call_refs.push_back(std::move(calls));
        ++partition_id;
    }

    if (partitions.empty())
        return {};

    parent_sets.resize(partitions.size());
    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        for (const auto& func : partitions[idx].Functions())
            addr_index[func.StartAddr()] = idx;
        id_index[partitions[idx].Id()] = idx;
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> dependency_set;
        std::set<std::string> unresolved_set;

        for (const auto& call : call_refs[idx]) {
            if (call.first.has_value()) {
                uint64_t target = call.first.value();
                auto it = addr_index.find(target);
                if (it != addr_index.end()) {
                    const std::string& child_id = partitions[it->second].Id();
                    if (child_id != partitions[idx].Id()) {
                        dependency_set.insert(child_id);
                        parent_sets[it->second].insert(partitions[idx].Id());
                    }
                } else {
                    unresolved_set.insert(UnresolvedLabel(call));
                }
            } else {
                unresolved_set.insert(UnresolvedLabel(call));
            }
        }

        partitions[idx].Dependencies().assign(dependency_set.begin(), dependency_set.end());
        partitions[idx].UnresolvedDependencies().assign(unresolved_set.begin(), unresolved_set.end());
    }

    for (size_t idx = 0; idx < partitions.size(); ++idx)
        partitions[idx].Parents().assign(parent_sets[idx].begin(), parent_sets[idx].end());

    auto resolves_to_partition = [&](size_t idx, const CallRef& call) {
        if (!call.first.has_value())
            return false;
        auto it = addr_index.find(call.first.value());
        if (it == addr_index.end())
            return false;
        const auto& child_id = partitions[it->second].Id();
        return child_id != partitions[idx].Id();
    };

    for (size_t idx = 0; idx < partitions.size(); ++idx) {
        std::set<std::string> names;
        bool needs_display = false;
        for (const auto& call : call_refs[idx]) {
            if (resolves_to_partition(idx, call))
                continue;
            auto symbol = NormalizeExternalSymbol(call);
            if (!symbol.empty()) {
                names.insert(symbol);
                if (!needs_display && IsGuiSymbol(symbol))
                    needs_display = true;
            }
        }
        partitions[idx].ExternalCalls() = std::move(names);
        partitions[idx].SetRequiresDisplay(needs_display);
        partitions[idx].SetBinHash(HashBytes(partitions[idx].RawBytes()));
    }

    for (auto& partition : partitions) {
        std::set<std::string> provided;
        for (const auto& parent_id : partition.Parents()) {
            auto it = id_index.find(parent_id);
            if (it == id_index.end())
                continue;
            const auto& outputs = partitions[it->second].Outputs();
            provided.insert(outputs.begin(), outputs.end());
        }

        std::set<std::string> external;
        std::set_difference(partition.Inputs().begin(), partition.Inputs().end(),
                            provided.begin(), provided.end(),
                            std::inserter(external, external.begin()));
        partition.ExternalInputs() = external;
    }

    return partitions;
}

}  // namespace splitter
