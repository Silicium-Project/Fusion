#include "splitter/pipeline/AnalysisPhase.hpp"

namespace splitter {

AnalysisPhase::AnalysisPhase(const IInstructionAnalyzer& analyzer)
    : analyzer_(analyzer) {}

void AnalysisPhase::Execute(PipelineContext& context) {
    for (auto& func : context.functions)
        analyzer_.AnalyzeFunctionLoops(func);
}

}  // namespace splitter
