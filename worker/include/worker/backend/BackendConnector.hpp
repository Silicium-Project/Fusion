#pragma once

#include <memory>
#include <string>
#include <vector>

#include "core/ExecutionResult.hpp"

#include "worker/backend/BackendRequest.hpp"
#include "worker/core/WorkerConfig.hpp"

namespace worker {

class IBackendConnector {
public:
    virtual ~IBackendConnector() = default;
    virtual fragment::ExecutionResult execute(const BackendRequest& request) = 0;
};

using BackendConnector = IBackendConnector;

std::unique_ptr<IBackendConnector> make_backend_connector(const WorkerConfig& config);

}  // namespace worker
