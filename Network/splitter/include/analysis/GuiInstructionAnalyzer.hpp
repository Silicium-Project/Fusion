#pragma once

#include "analysis/IInstructionAnalyzer.hpp"

namespace splitter {

// Analyseur spécialisé GUI : détecte des fonctions graphiques et marque un motif explicatif.
class GuiInstructionAnalyzer : public IInstructionAnalyzer {
public:
    static const GuiInstructionAnalyzer& Instance();

    void AnalyzeInstruction(Instruction&) const override;
    bool AnalyzeFunctionLoops(Function&) const override;
    LoopAnalysis DetectLoopPatterns(const Function& func) const override;

private:
    GuiInstructionAnalyzer() = default;
};

}  // namespace splitter
