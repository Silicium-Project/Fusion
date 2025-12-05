#include "analysis/ArmInstructionAnalyzer.hpp"

namespace splitter {

const ArmInstructionAnalyzer& ArmInstructionAnalyzer::Instance() {
    static ArmInstructionAnalyzer analyzer;
    return analyzer;
}

}  // namespace splitter
