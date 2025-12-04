#pragma once

#include <memory>

#include "splitter/artifacts/ArtifactBuilder.hpp"
#include "splitter/artifacts/SummaryWriter.hpp"
#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

class ArtifactsPhase : public IPipelinePhase {
public:
    ArtifactsPhase(std::unique_ptr<ArtifactBuilder> builder,
                   std::unique_ptr<SummaryWriter> summary_writer,
                   bool parallel = false);

    const char* Name() const override { return "Artifacts"; }
    void Execute(PipelineContext& context) override;

private:
    std::unique_ptr<ArtifactBuilder> builder_;
    std::unique_ptr<SummaryWriter> summary_writer_;
    bool parallel_;
};

}  // namespace splitter
