#pragma once

#include <string>
#include <vector>

#include "worker/task_report.hpp"
#include "worker/worker_config.hpp"

namespace worker {

struct WorkerReport {
    std::string summary_path;
    ExecutionMode mode = ExecutionMode::Auto;
    std::vector<TaskReport> tasks;
};

}  // namespace worker
