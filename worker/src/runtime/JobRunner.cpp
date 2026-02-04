#include "worker/runtime/JobRunner.hpp"

#include <stdexcept>

namespace worker {

static std::string resolve_path(const std::filesystem::path& base, const std::string& candidate) {
    if (candidate.empty())
        return "";

    std::filesystem::path path(candidate);
    if (path.is_absolute())
        return path.lexically_normal().string();

    auto normalize = [](const std::filesystem::path& p) {
        return std::filesystem::absolute(p).lexically_normal().string();
    };

    std::filesystem::path probe = base;
    while (true) {
        auto combined = (probe / path).lexically_normal();
        if (std::filesystem::exists(combined))
            return normalize(combined);
        if (!probe.has_parent_path())
            break;
        probe = probe.parent_path();
    }

    if (std::filesystem::exists(path))
        return normalize(path);

    return normalize((base / path).lexically_normal());
}

JobRunner::JobRunner(std::string summary_path, WorkerConfig config)
: summary_(fragment::load_partition_summary(summary_path))
, base_dir_(std::filesystem::path(summary_path).parent_path())
, resolved_binary_path_(resolve_path(base_dir_, summary_.binary_path))
, summary_path_(std::move(summary_path))
, worker_(std::move(config)) {
    if (!resolved_binary_path_.empty())
        summary_.binary_path = resolved_binary_path_;
    for (auto& partition : summary_.partitions) {
        partition.asm_path = resolve_path(base_dir_, partition.asm_path);
        if (!partition.bin_path.empty())
            partition.bin_path = resolve_path(base_dir_, partition.bin_path);
        if (!partition.wrapper_path.empty())
            partition.wrapper_path = resolve_path(base_dir_, partition.wrapper_path);
    }
    for (size_t idx = 0; idx < summary_.partitions.size(); ++idx)
        partition_index_.emplace(summary_.partitions[idx].id, idx);

    if (!summary_.initial_memory.empty()) {
        std::vector<MemorySnapshot> snapshots;
        snapshots.reserve(summary_.initial_memory.size());
        for (const auto& region : summary_.initial_memory) {
            MemorySnapshot snapshot;
            snapshot.address = region.address;
            snapshot.bytes = region.bytes;
            snapshots.push_back(std::move(snapshot));
        }
        worker_.load_initial_memory(snapshots);
    }
}

TaskReport JobRunner::execute(const Task& task) {
    if (task.type != TaskType::Binary) {
        fragment::PartitionInfo placeholder;
        placeholder.id = task.partition_id.empty() ? task_type_to_string(task.type) : task.partition_id;
        return worker_.run_task(placeholder, "", "", summary_path_, task);
    }

    auto it = partition_index_.find(task.partition_id);
    if (it == partition_index_.end())
        throw std::runtime_error("Partition inconnue: " + task.partition_id);

    const auto& partition = summary_.partitions[it->second];
    const std::string asm_path = resolve_path(base_dir_, partition.asm_path);
    fragment::set_partition_registry(&summary_.partitions);
    TaskReport report = worker_.run_task(partition, asm_path, resolved_binary_path_, summary_path_, task);
    fragment::set_partition_registry(nullptr);
    return report;
}

const fragment::PartitionSummary& JobRunner::summary() const {
    return summary_;
}

const std::string& JobRunner::summary_path() const {
    return summary_path_;
}

}  // namespace worker
