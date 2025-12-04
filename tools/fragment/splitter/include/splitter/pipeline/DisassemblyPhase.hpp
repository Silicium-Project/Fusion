#pragma once

#include <memory>

#include "splitter/analysis/IDisassembler.hpp"
#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

class DisassemblyPhase : public IPipelinePhase {
public:
    explicit DisassemblyPhase(std::unique_ptr<IDisassembler> disassembler);
    std::string Name() const override { return "Disassembly"; }
    void Execute(PipelineContext& context) override;

private:
    std::unique_ptr<IDisassembler> disassembler_;
};

}  // namespace splitter
