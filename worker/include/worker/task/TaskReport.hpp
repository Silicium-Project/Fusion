#pragma once

#include "core/ExecutionResult.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker {

struct TaskReport {
    PartitionId partition_id;
    RegisterState inputs;
    fragment::ExecutionResult result;
};

}  // namespace worker
