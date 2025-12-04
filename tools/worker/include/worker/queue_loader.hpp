#pragma once

#include <string>
#include <vector>

#include "worker/task.hpp"
#include "worker/task_types.hpp"

namespace worker {

std::vector<Task> load_queue_file(const std::string& path);
RegisterValue parse_register_value(const std::string& token);

}  // namespace worker
