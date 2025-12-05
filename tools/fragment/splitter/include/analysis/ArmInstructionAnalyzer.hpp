#pragma once

#include "analysis/IInstructionAnalyzer.hpp"

namespace splitter {

class ArmInstructionAnalyzer : public IInstructionAnalyzer {
public:
    static const ArmInstructionAnalyzer& Instance();

    void AnalyzeInstruction(Instruction&) const override {}
    bool AnalyzeFunctionLoops(Function&) const override { return false; }
    LoopAnalysis DetectLoopPatterns(const Function&) const override { return {false, ""}; }

private:
    ArmInstructionAnalyzer() = default;
};

}  // namespace splitter
