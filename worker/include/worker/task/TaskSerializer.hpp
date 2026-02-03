#pragma once

#include <string>
#include <vector>

#include "core/ExecutionResult.hpp"
#include "core/Config.hpp"
#include "worker/state/MemorySnapshot.hpp"
#include "worker/task/TaskTypes.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

struct TaskPayload {
    TaskType type = TaskType::Binary;
    PartitionId partition_id;
    std::string asm_path;
    std::string binary_path;
    ExecutionMode mode = ExecutionMode::Emulator;
    RegisterState inputs;
    RegisterState register_state;
    std::vector<MemorySnapshot> memory_state;
    std::vector<fragment::FdRule> fd_rules;
};

std::string serialize_task_payload(const TaskPayload& payload);

TaskPayload deserialize_task_payload(const std::string& content);

std::string serialize_execution_result(const fragment::ExecutionResult& result);

fragment::ExecutionResult deserialize_execution_result(const std::string& content);

}  // namespace worker
