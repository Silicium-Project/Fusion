#pragma once

#include "splitter/analysis/LoopAnalysis.hpp"
#include "splitter/core/Function.hpp"
#include "splitter/core/Instruction.hpp"

namespace splitter {

class IInstructionAnalyzer {
public:
    virtual ~IInstructionAnalyzer() = default;

    virtual void AnalyzeInstruction(Instruction& inst) const = 0;
    virtual bool AnalyzeFunctionLoops(Function& func) const = 0;
    virtual LoopAnalysis DetectLoopPatterns(const Function& func) const = 0;
};

}  // namespace splitter
