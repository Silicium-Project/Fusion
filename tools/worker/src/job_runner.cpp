#include "worker/job_runner.hpp"

#include <stdexcept>

namespace worker {

namespace {

std::string resolve_path(const std::filesystem::path& base, const std::string& candidate) {
    if (candidate.empty())
        return "";

    std::filesystem::path path(candidate);
    if (path.is_relative())
        path = base / path;
    path = path.lexically_normal();

    if (std::filesystem::exists(path))
        return path.string();

    if (path.is_absolute() || !base.has_parent_path())
        return path.string();

    auto fallback = (base.parent_path() / std::filesystem::path(candidate)).lexically_normal();
    if (std::filesystem::exists(fallback))
        return fallback.string();

    return path.string();
}

}  // namespace

JobRunner::JobRunner(std::string summary_path, WorkerConfig config)
: summary_(fragment::load_partition_summary(summary_path))
, base_dir_(std::filesystem::path(summary_path).parent_path())
, resolved_binary_path_(resolve_path(base_dir_, summary_.binary_path))
, summary_path_(std::move(summary_path))
, worker_(std::move(config)) {
    for (size_t idx = 0; idx < summary_.partitions.size(); ++idx)
        partition_index_.emplace(summary_.partitions[idx].id, idx);
}

TaskReport JobRunner::execute(const Task& task) {
    auto it = partition_index_.find(task.partition_id);
    if (it == partition_index_.end())
        throw std::runtime_error("Partition inconnue: " + task.partition_id);

    const auto& partition = summary_.partitions[it->second];
    const std::string asm_path = resolve_path(base_dir_, partition.asm_path);

    std::string binary_path = resolve_path(base_dir_, partition.bin_path);
    if (binary_path.empty())
        binary_path = resolved_binary_path_;

    return worker_.run_task(partition, asm_path, binary_path, task);
}

}  // namespace worker
