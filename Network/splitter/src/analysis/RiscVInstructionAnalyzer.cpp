#include "analysis/RiscVInstructionAnalyzer.hpp"

namespace splitter {

const RiscVInstructionAnalyzer& RiscVInstructionAnalyzer::Instance() {
    static RiscVInstructionAnalyzer analyzer;
    return analyzer;
}

void RiscVInstructionAnalyzer::AnalyzeInstruction(Instruction&) const {}

bool RiscVInstructionAnalyzer::AnalyzeFunctionLoops(Function&) const {
    return false;
}

LoopAnalysis RiscVInstructionAnalyzer::DetectLoopPatterns(const Function&) const {
    return {false, ""};
}

}  // namespace splitter
