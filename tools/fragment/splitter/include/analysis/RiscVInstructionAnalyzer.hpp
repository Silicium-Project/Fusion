#pragma once

#include "analysis/IInstructionAnalyzer.hpp"

namespace splitter {

class RiscVInstructionAnalyzer : public IInstructionAnalyzer {
public:
    static const RiscVInstructionAnalyzer& Instance();

    void AnalyzeInstruction(Instruction&) const override {}
    bool AnalyzeFunctionLoops(Function&) const override { return false; }
    LoopAnalysis DetectLoopPatterns(const Function&) const override { return {false, ""}; }

private:
    RiscVInstructionAnalyzer() = default;
};

}  // namespace splitter
