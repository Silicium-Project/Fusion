#pragma once

#include <memory>

#include "analysis/IInstructionAnalyzer.hpp"
#include "pipeline/IPipelinePhase.hpp"

namespace splitter {

class AnalysisPhase : public IPipelinePhase {
public:
    explicit AnalysisPhase(std::shared_ptr<const IInstructionAnalyzer> analyzer);
    std::string Name() const override;
    void Execute(PipelineContext& context) override;

private:
    std::shared_ptr<const IInstructionAnalyzer> analyzer_;
};

}  // namespace splitter
