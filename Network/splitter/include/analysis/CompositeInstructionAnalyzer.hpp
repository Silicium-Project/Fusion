#pragma once

#include <functional>
#include <vector>

#include "analysis/IInstructionAnalyzer.hpp"
#include "analysis/GuiInstructionAnalyzer.hpp"

namespace splitter {

// Chaîne d'analyseurs : permet de composer plusieurs implémentations sans multiplier les classes.
class CompositeInstructionAnalyzer : public IInstructionAnalyzer {
public:
    CompositeInstructionAnalyzer() = default;

    static const CompositeInstructionAnalyzer& Default();

    void AddAnalyzer(const IInstructionAnalyzer& analyzer);

    void AnalyzeInstruction(Instruction& inst) const override;
    bool AnalyzeFunctionLoops(Function& func) const override;
    LoopAnalysis DetectLoopPatterns(const Function& func) const override;

private:
    std::vector<std::reference_wrapper<const IInstructionAnalyzer>> analyzers_;
};

}  // namespace splitter
