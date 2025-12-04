#pragma once

#include "fragment/execution_result.hpp"
#include "worker/task_types.hpp"

namespace worker {

struct TaskReport {
    PartitionId partition_id;
    RegisterState inputs;
    fragment::ExecutionResult result;
};

}  // namespace worker
