#pragma once

#include <string>
#include <vector>

#include "partition/PartitionSummary.hpp"
#include "core/Config.hpp"

#include "worker/state/MemorySnapshot.hpp"
#include "worker/task/TaskTypes.hpp"

namespace worker {

struct BackendRequest {
    const fragment::PartitionInfo& partition;
    std::string summary_path;
    std::string asm_path;
    std::string binary_path;
    RegisterState inputs;
    RegisterState register_state;
    std::vector<MemorySnapshot> memory_state;
    std::vector<fragment::FdRule> fd_rules;
};

}  // namespace worker
