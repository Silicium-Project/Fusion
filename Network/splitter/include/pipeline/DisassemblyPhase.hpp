#pragma once

#include <memory>

#include "analysis/IDisassembler.hpp"
#include "pipeline/IPipelinePhase.hpp"

namespace splitter {

class DisassemblyPhase : public IPipelinePhase {
public:
    explicit DisassemblyPhase(std::unique_ptr<IDisassembler> disassembler);
    std::string Name() const override;
    void Execute(PipelineContext& context) override;
    std::vector<std::string> Inputs() const override;
    std::vector<std::string> Outputs() const override;

private:
    std::unique_ptr<IDisassembler> disassembler_;
};

}  // namespace splitter
