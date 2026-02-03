#pragma once

#include <memory>
#include <string>
#include <vector>

#include "core/ExecutionResult.hpp"

#include "worker/backend/BackendRequest.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class BackendConnector {
public:
    virtual ~BackendConnector() = default;
    virtual fragment::ExecutionResult execute(const BackendRequest& request) = 0;
};

std::unique_ptr<BackendConnector> make_backend_connector(const WorkerConfig& config);

}  // namespace worker
