#pragma once

#include "analysis/IInstructionAnalyzer.hpp"

namespace splitter {

class ArmInstructionAnalyzer : public IInstructionAnalyzer {
public:
    static const ArmInstructionAnalyzer& Instance();

    void AnalyzeInstruction(Instruction&) const override;
    bool AnalyzeFunctionLoops(Function&) const override;
    LoopAnalysis DetectLoopPatterns(const Function&) const override;

private:
    ArmInstructionAnalyzer() = default;
};

}  // namespace splitter
