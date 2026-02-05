#include "pipeline/PartitioningPhase.hpp"

#include "partitioning/BinaryExtractor.hpp"

namespace splitter {

PartitioningPhase::PartitioningPhase(std::unique_ptr<IPartitioner> partitioner,
                                     std::shared_ptr<BinaryExtractor> extractor)
    : partitioner_(std::move(partitioner)), extractor_(std::move(extractor)) {}

std::string PartitioningPhase::Name() const {
    return "Partitioning";
}

std::vector<std::string> PartitioningPhase::Inputs() const {
    return {"functions"};
}

std::vector<std::string> PartitioningPhase::Outputs() const {
    return {"partitions", "memory_segments"};
}

void PartitioningPhase::Execute(PipelineContext& context) {
    context.partitions = partitioner_->Run(context.functions);
    if (extractor_)
        context.memory_segments = extractor_->ExtractDataSections(context.config.binary_path.Value());
}

}  // namespace splitter
