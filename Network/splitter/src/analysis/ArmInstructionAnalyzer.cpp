#include "analysis/ArmInstructionAnalyzer.hpp"

namespace splitter {

const ArmInstructionAnalyzer& ArmInstructionAnalyzer::Instance() {
    static ArmInstructionAnalyzer analyzer;
    return analyzer;
}

void ArmInstructionAnalyzer::AnalyzeInstruction(Instruction&) const {}

bool ArmInstructionAnalyzer::AnalyzeFunctionLoops(Function&) const {
    return false;
}

LoopAnalysis ArmInstructionAnalyzer::DetectLoopPatterns(const Function&) const {
    return {false, ""};
}

}  // namespace splitter
