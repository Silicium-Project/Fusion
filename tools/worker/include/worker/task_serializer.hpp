#pragma once

#include <map>
#include <string>
#include <vector>

#include "fragment/execution_result.hpp"
#include "worker/memory_snapshot.hpp"

namespace worker {

struct TaskPayload {
    std::string partition_id;
    std::string asm_path;
    std::string binary_path;
    bool native_mode = false;
    std::map<std::string, uint64_t> inputs;
    std::map<std::string, uint64_t> register_state;
    std::vector<MemorySnapshot> memory_state;
};

std::string serialize_task_payload(const TaskPayload& payload);

TaskPayload deserialize_task_payload(const std::string& content);

std::string serialize_execution_result(const fragment::ExecutionResult& result);

fragment::ExecutionResult deserialize_execution_result(const std::string& content);

}  // namespace worker
