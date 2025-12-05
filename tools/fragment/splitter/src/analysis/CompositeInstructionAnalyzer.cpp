#include "splitter/analysis/CompositeInstructionAnalyzer.hpp"

#include "splitter/analysis/X86InstructionAnalyzer.hpp"

namespace splitter {

const CompositeInstructionAnalyzer& CompositeInstructionAnalyzer::Default() {
    static CompositeInstructionAnalyzer instance;
    static bool initialized = false;
    if (!initialized) {
        instance.AddAnalyzer(X86_64InstructionAnalyzer::Instance());
        instance.AddAnalyzer(GuiInstructionAnalyzer::Instance());
        initialized = true;
    }
    return instance;
}

void CompositeInstructionAnalyzer::AddAnalyzer(const IInstructionAnalyzer& analyzer) {
    analyzers_.push_back(std::cref(analyzer));
}

void CompositeInstructionAnalyzer::AnalyzeInstruction(Instruction& inst) const {
    for (const auto& analyzer_ref : analyzers_) {
        const IInstructionAnalyzer& analyzer = analyzer_ref;
        analyzer.AnalyzeInstruction(inst);
    }
}

bool CompositeInstructionAnalyzer::AnalyzeFunctionLoops(Function& func) const {
    bool modified = false;
    for (const auto& analyzer_ref : analyzers_) {
        const IInstructionAnalyzer& analyzer = analyzer_ref;
        modified = analyzer.AnalyzeFunctionLoops(func) || modified;
    }
    return modified;
}

LoopAnalysis CompositeInstructionAnalyzer::DetectLoopPatterns(const Function& func) const {
    LoopAnalysis result{false, {}};
    for (const auto& analyzer_ref : analyzers_) {
        const IInstructionAnalyzer& analyzer = analyzer_ref;
        auto current = analyzer.DetectLoopPatterns(func);
        // Conserver la première réponse positive, sinon garder le dernier motif explicatif.
        if (current.parallelizable)
            return current;
        if (!current.reason.empty())
            result = current;
    }
    return result;
}

}  // namespace splitter
