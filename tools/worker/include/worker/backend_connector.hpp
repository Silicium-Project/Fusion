#pragma once

#include <map>
#include <memory>
#include <string>
#include <vector>

#include "fragment/execution_result.hpp"

#include "worker/memory_snapshot.hpp"
#include "worker/task_serializer.hpp"
#include "worker/types.hpp"

namespace fragment {
struct PartitionInfo;
}

namespace worker {

struct BackendRequest {
    const fragment::PartitionInfo& partition;
    std::string asm_path;
    std::string binary_path;
    std::map<std::string, uint64_t> inputs;
    std::map<std::string, uint64_t> register_state;
    std::vector<MemorySnapshot> memory_state;
};

class BackendConnector {
public:
    virtual ~BackendConnector() = default;
    virtual fragment::ExecutionResult execute(const BackendRequest& request) = 0;
};

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config);

}  // namespace worker

