#pragma once

#include "worker/task/TaskTypes.hpp"

namespace worker {

struct Task {
    PartitionId partition_id;
    RegisterState inputs;
};

}  // namespace worker
