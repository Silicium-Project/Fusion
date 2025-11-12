#pragma once

#include <map>
#include <string>
#include <vector>

#include "fragment/config.hpp"
#include "fragment/execution_result.hpp"

namespace worker {

struct Task {
    std::string partition_id;
    std::map<std::string, uint64_t> inputs;
};

struct WorkerConfig {
    fragment::ExecutorConfig executor;
    bool native_mode = false;
};

struct TaskReport {
    std::string partition_id;
    std::map<std::string, uint64_t> inputs;
    fragment::ExecutionResult result;
};

struct WorkerReport {
    std::string summary_path;
    bool native_mode = false;
    std::vector<TaskReport> tasks;
};

}  // namespace worker
