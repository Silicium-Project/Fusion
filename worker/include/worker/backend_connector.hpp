#pragma once

#include <memory>
#include <string>
#include <vector>

#include "ExecutionResult.hpp"
#include "Config.hpp"

#include "worker/memory_snapshot.hpp"
#include "worker/task_serializer.hpp"
#include "worker/task_types.hpp"
#include "worker/worker_config.hpp"

namespace fragment {
struct PartitionInfo;
}

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

class BackendConnector {
public:
    virtual ~BackendConnector() = default;
    virtual fragment::ExecutionResult execute(const BackendRequest& request) = 0;
};

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config);

}  // namespace worker
