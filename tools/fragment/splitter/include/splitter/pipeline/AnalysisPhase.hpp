#pragma once

#include <memory>

#include "splitter/analysis/IInstructionAnalyzer.hpp"
#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

class AnalysisPhase : public IPipelinePhase {
public:
    explicit AnalysisPhase(const IInstructionAnalyzer& analyzer);
    std::string Name() const override { return "Analysis"; }
    void Execute(PipelineContext& context) override;

private:
    const IInstructionAnalyzer& analyzer_;
};

}  // namespace splitter
