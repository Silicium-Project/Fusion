#include "pipeline/ArtifactsPhase.hpp"

#include <thread>
#include <vector>
#include <filesystem>

namespace splitter {

ArtifactsPhase::ArtifactsPhase(std::unique_ptr<ArtifactBuilder> builder,
                               std::unique_ptr<SummaryWriter> summary_writer,
                               bool parallel)
    : builder_(std::move(builder)),
      summary_writer_(std::move(summary_writer)),
      parallel_(parallel) {}

std::string ArtifactsPhase::Name() const {
    return "Artifacts";
}

std::vector<std::string> ArtifactsPhase::Inputs() const {
    return {"partitions", "memory_segments"};
}

std::vector<std::string> ArtifactsPhase::Outputs() const {
    return {"artifacts", "summary"};
}

void ArtifactsPhase::Execute(PipelineContext& context) {
    context.artifacts.clear();
    context.artifacts.reserve(context.partitions.size());

    if (parallel_) {
        std::vector<PartitionFiles> artifacts(context.partitions.size());
        std::vector<std::thread> workers;
        workers.reserve(context.partitions.size());
        for (std::size_t idx = 0; idx < context.partitions.size(); ++idx) {
            workers.emplace_back([this, &context, idx, &artifacts]() {
                artifacts[idx] = builder_->CreatePartition(context.partitions[idx]);
            });
        }
        for (auto& worker : workers)
            worker.join();
        context.artifacts = std::move(artifacts);
    } else {
        for (const auto& partition : context.partitions)
            context.artifacts.push_back(builder_->CreatePartition(partition));
    }

    summary_writer_->Write(context.partitions, context.artifacts, context.memory_segments,
                           std::filesystem::path(context.config.binary_path.Value()));
}

}  // namespace splitter
