#include "partitioning/Partitioner.hpp"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <utility>

#include "partitioning/PartitionGraphBuilder.hpp"
#include "support/FlatSet.hpp"

namespace splitter {

namespace {

bool ShouldSkipFunction(const Function& func) {
    if (func.Name().empty())
        return true;
    if (func.Name() == "_start" || func.Name().find("_start") != std::string::npos)
        return true;  // bootstrap incompatible avec exécution native hors process complet
    return func.Name().find("@plt") != std::string::npos;
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

Partitioner::Partitioner(BinaryPath binary_path,
                         std::shared_ptr<const IInstructionAnalyzer> analyzer,
                         std::shared_ptr<BinaryExtractor> extractor,
                         HashService hash_service)
    : binary_path_(std::move(binary_path)),
      analyzer_(std::move(analyzer)),
      extractor_(std::move(extractor)),
      graph_builder_(std::move(hash_service)) {}

std::vector<Partition> Partitioner::Run(std::vector<Function>& functions) {
    std::vector<Partition> partitions;
    CallMatrix call_refs;

    int partition_id = 0;
    for (auto& func : functions) {
        if (ShouldSkipFunction(func))
            continue;

        std::optional<LoopAnalysis> loop_info;
        if (func.HasLoopAnalysis())
            loop_info = func.LoopAnalysisInfo();
        if (!loop_info.has_value() && analyzer_) {
            for (auto& inst : func.Instructions())
                analyzer_->AnalyzeInstruction(inst);
            analyzer_->AnalyzeFunctionLoops(func);
            loop_info = analyzer_->DetectLoopPatterns(func);
            func.SetLoopAnalysis(*loop_info);
        }

        Partition partition;
        partition.SetId("func_" + std::to_string(partition_id) + "_" + func.Name());
        partition.Functions().push_back(func);
        partition.SetStartAddr(func.StartAddr());
        partition.SetEndAddr(func.EndAddr());
        partition.SetAsmCode(FunctionToAsm(func));
        if (func.EndAddr() > func.StartAddr() && extractor_) {
            partition.RawBytes() =
                extractor_->ExtractSegment(binary_path_.Value(), func.StartAddr(), func.EndAddr());
        }
        if (loop_info.has_value())
            partition.SetIsParallelizable(loop_info->parallelizable);

        FlatStringSet outputs;
        FlatStringSet observed_inputs;
        FlatStringSet written_registers;
        std::vector<CallRef> calls;

        for (const auto& inst : func.Instructions()) {
            for (const auto& reg : inst.Reads())
                if (!written_registers.contains(reg))
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
    graph_builder_.BuildGraph(partitions, call_refs);
    return partitions;
}

}  // namespace splitter
