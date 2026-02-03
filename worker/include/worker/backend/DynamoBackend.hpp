#pragma once

#include <memory>

#include "core/ExecutionResult.hpp"

#include "worker/backend/BackendRequest.hpp"
#include "worker/runtime/DynamoRunner.hpp"
#include "worker/task/TaskSerializer.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class DynamoBackend {
public:
    explicit DynamoBackend(const WorkerConfig& config);

    fragment::ExecutionResult execute(const BackendRequest& request);

private:
    const WorkerConfig& config_;
    std::unique_ptr<DynamoRunner> dynamo_runner_;
};

}  // namespace worker
