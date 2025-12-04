#include "splitter/pipeline/ArtifactsPhase.hpp"

#include <future>

namespace splitter {

ArtifactsPhase::ArtifactsPhase(std::unique_ptr<ArtifactBuilder> builder,
                               std::unique_ptr<SummaryWriter> summary_writer,
                               bool parallel)
    : builder_(std::move(builder)),
      summary_writer_(std::move(summary_writer)),
      parallel_(parallel) {}

void ArtifactsPhase::Execute(PipelineContext& context) {
    context.artifacts.clear();
    context.artifacts.reserve(context.partitions.size());

    if (parallel_) {
        std::vector<std::future<PartitionFiles>> futures;
        futures.reserve(context.partitions.size());
        for (const auto& partition : context.partitions) {
            futures.emplace_back(std::async(std::launch::async, [&builder = *builder_, &partition]() {
                return builder.CreatePartition(partition);
            }));
        }
        for (auto& future : futures)
            context.artifacts.push_back(future.get());
    } else {
        for (const auto& partition : context.partitions)
            context.artifacts.push_back(builder_->CreatePartition(partition));
    }

    summary_writer_->Write(context.partitions, context.artifacts, context.memory_segments,
                           context.config.binary_path.Value());
}

}  // namespace splitter
