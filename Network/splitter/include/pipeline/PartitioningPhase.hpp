#pragma once

#include <memory>

#include <memory>

#include "partitioning/IPartitioner.hpp"
#include "partitioning/Partitioner.hpp"
#include <memory>

#include "pipeline/IPipelinePhase.hpp"

namespace splitter {

class PartitioningPhase : public IPipelinePhase {
public:
    PartitioningPhase(std::unique_ptr<IPartitioner> partitioner,
                      std::shared_ptr<BinaryExtractor> extractor);
    std::string Name() const override;
    void Execute(PipelineContext& context) override;
    std::vector<std::string> Inputs() const override;
    std::vector<std::string> Outputs() const override;

private:
    std::unique_ptr<IPartitioner> partitioner_;
    std::shared_ptr<BinaryExtractor> extractor_;
};

}  // namespace splitter
