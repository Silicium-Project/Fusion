#pragma once

#include <memory>

#include "artifacts/ArtifactBuilder.hpp"
#include "artifacts/SummaryWriter.hpp"
#include "pipeline/IPipelinePhase.hpp"

namespace splitter {

class ArtifactsPhase : public IPipelinePhase {
public:
    ArtifactsPhase(std::unique_ptr<ArtifactBuilder> builder,
                   std::unique_ptr<SummaryWriter> summary_writer,
                   bool parallel = false);

    std::string Name() const override;
    void Execute(PipelineContext& context) override;
    std::vector<std::string> Inputs() const override;
    std::vector<std::string> Outputs() const override;

private:
    std::unique_ptr<ArtifactBuilder> builder_;
    std::unique_ptr<SummaryWriter> summary_writer_;
    bool parallel_;
};

}  // namespace splitter
