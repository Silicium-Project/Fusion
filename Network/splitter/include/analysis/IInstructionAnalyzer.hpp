#pragma once

#include "analysis/LoopAnalysis.hpp"
#include "core/Function.hpp"
#include "core/Instruction.hpp"

namespace splitter {

class IInstructionAnalyzer {
public:
    virtual ~IInstructionAnalyzer() = default;

    virtual void AnalyzeInstruction(Instruction& inst) const = 0;
    virtual bool AnalyzeFunctionLoops(Function& func) const = 0;
    virtual LoopAnalysis DetectLoopPatterns(const Function& func) const = 0;
};

}  // namespace splitter
