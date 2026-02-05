#include "pipeline/AnalysisPhase.hpp"

namespace splitter {

AnalysisPhase::AnalysisPhase(std::shared_ptr<const IInstructionAnalyzer> analyzer)
    : analyzer_(std::move(analyzer)) {}

std::string AnalysisPhase::Name() const {
    return "Analysis";
}

std::vector<std::string> AnalysisPhase::Inputs() const {
    return {"functions", "disassembly"};
}

std::vector<std::string> AnalysisPhase::Outputs() const {
    return {"functions"};
}

void AnalysisPhase::Execute(PipelineContext& context) {
    for (auto& func : context.functions)
        analyzer_->AnalyzeFunctionLoops(func);
}

}  // namespace splitter
