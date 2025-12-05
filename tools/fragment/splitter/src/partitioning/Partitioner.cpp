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
    if (func.Name().front() == '_')
        return true;
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
                         const IInstructionAnalyzer& analyzer,
                         std::shared_ptr<BinaryExtractor> extractor,
                         HashService hash_service)
    : binary_path_(std::move(binary_path)),
      analyzer_(analyzer),
      extractor_(std::move(extractor)),
      graph_builder_(std::move(hash_service)) {}

std::vector<Partition> Partitioner::Run(std::vector<Function>& functions) {
    std::vector<Partition> partitions;
    CallMatrix call_refs;

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
        if (func.EndAddr() > func.StartAddr() && extractor_) {
            partition.RawBytes() =
                extractor_->ExtractSegment(binary_path_.Value(), func.StartAddr(), func.EndAddr());
        }
        partition.SetIsParallelizable(loop_info.parallelizable);

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
