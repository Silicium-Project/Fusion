#include "pipeline/AnalysisPhase.hpp"

namespace splitter {

AnalysisPhase::AnalysisPhase(std::shared_ptr<const IInstructionAnalyzer> analyzer)
    : analyzer_(std::move(analyzer)) {}

void AnalysisPhase::Execute(PipelineContext& context) {
    for (auto& func : context.functions)
        analyzer_->AnalyzeFunctionLoops(func);
}

}  // namespace splitter
