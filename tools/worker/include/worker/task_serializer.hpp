#pragma once

#include <string>
#include <vector>

#include "fragment/execution_result.hpp"
#include "worker/memory_snapshot.hpp"
#include "worker/task_types.hpp"

namespace worker {

struct TaskPayload {
    PartitionId partition_id;
    std::string asm_path;
    std::string binary_path;
    bool native_mode = false;
    RegisterState inputs;
    RegisterState register_state;
    std::vector<MemorySnapshot> memory_state;
};

std::string serialize_task_payload(const TaskPayload& payload);

TaskPayload deserialize_task_payload(const std::string& content);

std::string serialize_execution_result(const fragment::ExecutionResult& result);

fragment::ExecutionResult deserialize_execution_result(const std::string& content);

}  // namespace worker
