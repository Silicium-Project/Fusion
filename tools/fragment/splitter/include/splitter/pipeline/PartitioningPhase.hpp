#pragma once

#include <memory>

#include <memory>

#include "splitter/partitioning/IPartitioner.hpp"
#include "splitter/partitioning/Partitioner.hpp"
#include "splitter/pipeline/IPipelinePhase.hpp"

namespace splitter {

class PartitioningPhase : public IPipelinePhase {
public:
    PartitioningPhase(std::unique_ptr<IPartitioner> partitioner, const BinaryExtractor& extractor);
    const char* Name() const override { return "Partitioning"; }
    void Execute(PipelineContext& context) override;

private:
    std::unique_ptr<IPartitioner> partitioner_;
    const BinaryExtractor& extractor_;
};

}  // namespace splitter
