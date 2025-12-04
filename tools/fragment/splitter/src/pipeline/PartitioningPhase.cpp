#include "splitter/pipeline/PartitioningPhase.hpp"

#include "splitter/partitioning/BinaryExtractor.hpp"

namespace splitter {

PartitioningPhase::PartitioningPhase(std::unique_ptr<IPartitioner> partitioner, const BinaryExtractor& extractor)
    : partitioner_(std::move(partitioner)), extractor_(extractor) {}

void PartitioningPhase::Execute(PipelineContext& context) {
    context.partitions = partitioner_->Run(context.functions);
    context.memory_segments = extractor_.ExtractDataSections(context.config.binary_path.Value());
}

}  // namespace splitter
