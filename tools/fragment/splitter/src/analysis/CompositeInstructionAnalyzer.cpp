#include "splitter/analysis/CompositeInstructionAnalyzer.hpp"

#include "splitter/analysis/X86InstructionAnalyzer.hpp"

namespace splitter {

const CompositeInstructionAnalyzer& CompositeInstructionAnalyzer::Default() {
    static CompositeInstructionAnalyzer instance;
    static bool initialized = false;
    if (!initialized) {
        instance.AddAnalyzer(X86InstructionAnalyzer::Instance());
        instance.AddAnalyzer(GuiInstructionAnalyzer::Instance());
        initialized = true;
    }
    return instance;
}

void CompositeInstructionAnalyzer::AddAnalyzer(const IInstructionAnalyzer& analyzer) {
    analyzers_.push_back(std::cref(analyzer));
}

void CompositeInstructionAnalyzer::AnalyzeInstruction(Instruction& inst) const {
    for (const auto& analyzer : analyzers_)
        analyzer.get().AnalyzeInstruction(inst);
}

bool CompositeInstructionAnalyzer::AnalyzeFunctionLoops(Function& func) const {
    bool modified = false;
    for (const auto& analyzer : analyzers_)
        modified = analyzer.get().AnalyzeFunctionLoops(func) || modified;
    return modified;
}

LoopAnalysis CompositeInstructionAnalyzer::DetectLoopPatterns(const Function& func) const {
    LoopAnalysis result{false, {}};
    for (const auto& analyzer : analyzers_) {
        auto current = analyzer.get().DetectLoopPatterns(func);
        // Conserver la première réponse positive, sinon garder le dernier motif explicatif.
        if (current.parallelizable)
            return current;
        if (!current.reason.empty())
            result = current;
    }
    return result;
}

}  // namespace splitter
