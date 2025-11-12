#pragma once

#include "worker/types.hpp"

namespace worker {

std::vector<Task> load_queue_file(const std::string& path);
uint64_t parse_register_value(const std::string& token);

}  // namespace worker
