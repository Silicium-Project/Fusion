#pragma once

#include "ExecutionResult.hpp"
#include "worker/task_types.hpp"

namespace worker {

struct TaskReport {
    PartitionId partition_id;
    RegisterState inputs;
    fragment::ExecutionResult result;
};

}  // namespace worker
