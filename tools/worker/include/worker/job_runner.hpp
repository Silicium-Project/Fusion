#pragma once

#include <filesystem>
#include <string>
#include <unordered_map>

#include "fragment/partition_summary.hpp"

#include "worker/types.hpp"
#include "worker/worker.hpp"

namespace worker {

class JobRunner {
public:
    JobRunner(std::string summary_path, WorkerConfig config = {});

    TaskReport execute(const Task& task);
    const fragment::PartitionSummary& summary() const { return summary_; }
    const std::string& summary_path() const { return summary_path_; }

private:
    fragment::PartitionSummary summary_;
    std::unordered_map<std::string, size_t> partition_index_;
    std::filesystem::path base_dir_;
    std::string resolved_binary_path_;
    std::string summary_path_;
    Worker worker_;
};

}  // namespace worker
