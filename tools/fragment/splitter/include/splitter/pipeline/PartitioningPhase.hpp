#pragma once

#include <memory>

#include <memory>

#include "splitter/partitioning/IPartitioner.hpp"
#include "splitter/partitioning/Partitioner.hpp"
#include <memory>

#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

class PartitioningPhase : public IPipelinePhase {
public:
    PartitioningPhase(std::unique_ptr<IPartitioner> partitioner,
                      std::shared_ptr<BinaryExtractor> extractor);
    std::string Name() const override { return "Partitioning"; }
    void Execute(PipelineContext& context) override;

private:
    std::unique_ptr<IPartitioner> partitioner_;
    std::shared_ptr<BinaryExtractor> extractor_;
};

}  // namespace splitter
