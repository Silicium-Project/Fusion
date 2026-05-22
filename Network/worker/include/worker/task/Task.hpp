#pragma once

#include "worker/task/TaskTypes.hpp"

namespace worker {

struct Task {
    TaskType type = TaskType::Binary;
    PartitionId partition_id;
    RegisterState inputs;
};

}  // namespace worker
