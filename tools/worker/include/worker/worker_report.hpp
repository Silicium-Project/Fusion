#pragma once

#include <string>
#include <vector>

#include "worker/task_report.hpp"

namespace worker {

struct WorkerReport {
    std::string summary_path;
    bool native_mode = false;
    std::vector<TaskReport> tasks;
};

}  // namespace worker
