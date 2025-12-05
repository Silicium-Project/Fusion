#include "analysis/RiscVInstructionAnalyzer.hpp"

namespace splitter {

const RiscVInstructionAnalyzer& RiscVInstructionAnalyzer::Instance() {
    static RiscVInstructionAnalyzer analyzer;
    return analyzer;
}

}  // namespace splitter
