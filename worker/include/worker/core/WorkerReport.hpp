#pragma once

#include <string>
#include <vector>

#include "worker/task/TaskReport.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

struct WorkerReport {
    std::string summary_path;
    ExecutionMode mode = ExecutionMode::Auto;
    std::vector<TaskReport> tasks;
};

}  // namespace worker
