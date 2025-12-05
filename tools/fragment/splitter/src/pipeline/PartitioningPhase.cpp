#include "pipeline/PartitioningPhase.hpp"

#include "partitioning/BinaryExtractor.hpp"

namespace splitter {

PartitioningPhase::PartitioningPhase(std::unique_ptr<IPartitioner> partitioner,
                                     std::shared_ptr<BinaryExtractor> extractor)
    : partitioner_(std::move(partitioner)), extractor_(std::move(extractor)) {}

void PartitioningPhase::Execute(PipelineContext& context) {
    context.partitions = partitioner_->Run(context.functions);
    if (extractor_)
        context.memory_segments = extractor_->ExtractDataSections(context.config.binary_path.Value());
}

}  // namespace splitter
