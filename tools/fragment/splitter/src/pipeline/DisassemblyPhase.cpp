#include "pipeline/DisassemblyPhase.hpp"

namespace splitter {

DisassemblyPhase::DisassemblyPhase(std::unique_ptr<IDisassembler> disassembler)
    : disassembler_(std::move(disassembler)) {}

void DisassemblyPhase::Execute(PipelineContext& context) {
    auto result = disassembler_->Run();
    context.functions = std::move(result.first);
    context.disassembly = std::move(result.second);
}

}  // namespace splitter
