#pragma once

#include "worker/task_types.hpp"

namespace worker {

struct Task {
    PartitionId partition_id;
    RegisterState inputs;
};

}  // namespace worker
