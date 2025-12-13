#include "analysis/GuiInstructionAnalyzer.hpp"

#include <algorithm>
#include <string_view>

namespace splitter {

const GuiInstructionAnalyzer& GuiInstructionAnalyzer::Instance() {
    static GuiInstructionAnalyzer instance;
    return instance;
}

void GuiInstructionAnalyzer::AnalyzeInstruction(Instruction&) const {}

bool GuiInstructionAnalyzer::AnalyzeFunctionLoops(Function&) const {
    return false;
}

LoopAnalysis GuiInstructionAnalyzer::DetectLoopPatterns(const Function& func) const {
    static const std::string_view keywords[] = {"gui", "render", "display", "window"};
    std::string lower = func.Name();
    std::transform(lower.begin(), lower.end(), lower.begin(), [](unsigned char c) { return std::tolower(c); });
    for (auto key : keywords) {
        if (lower.find(key) != std::string::npos)
            return {false, "gui-bound"};
    }
    return {false, ""};
}

}  // namespace splitter
