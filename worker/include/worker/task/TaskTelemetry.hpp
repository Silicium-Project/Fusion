#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "worker/task/TaskTypes.hpp"

namespace worker {

struct TaskTelemetry {
    std::string task_id;
    TaskType type = TaskType::Binary;
    std::string status;
    std::uint64_t started_at_ms = 0;
    std::uint64_t finished_at_ms = 0;
    std::uint64_t duration_ms = 0;
    std::string linux_policy;
    std::string windows_policy;
    bool wsl_enabled = false;
    std::string wsl_decision;
    std::vector<std::string> warnings;
};

}  // namespace worker
